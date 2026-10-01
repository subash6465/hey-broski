import time
import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService
from app.credential_vault import CredentialVault
from app.connectors import ConnectorService
from app.mail_sync import MailSync
from app.repository import Repository


def test_profile_connection_and_real_mail_import(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.vault = CredentialVault(tmp_path)
    main.assistant = AssistantService(repository, main.settings)

    def provider(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/token":
            return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh", "token_type": "Bearer"})
        if path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "owner@example.com"})
        if path.endswith("/messages"):
            if "q" not in request.url.params:
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(200, json={"messages": [{"id": "gmail-1"}]})
        if path.endswith("/messages/gmail-1"):
            return httpx.Response(200, json={"id": "gmail-1", "internalDate": "1790870400000", "labelIds": ["INBOX"],
                "snippet": "Your insurance renews on 20 October 2026.",
                "payload": {"headers": [{"name": "Subject", "value": "Insurance renewal"}, {"name": "From", "value": "Insurer <hello@example.com>"}]}})
        raise AssertionError(f"Unexpected provider request: {request.url}")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))

    with TestClient(main.app) as client:
        assert client.get("/api/onboarding").json()["ready"] is False
        assert client.post("/api/accounts/gmail/start").status_code == 409
        profile = {"first_name": "Asha", "last_name": "Rao", "age": 29, "phone_number": "+91 98765 43210", "gender": "woman", "time_zone": "Asia/Kolkata"}
        assert client.put("/api/profile", json=profile).status_code == 200
        assert client.post("/api/accounts/gmail/client", json={"credentials": {"installed": {"client_id": "abc.apps.googleusercontent.com", "client_secret": "secret"}}}).status_code == 200
        start = client.post("/api/accounts/gmail/start").json()["authorization_url"]
        state = parse_qs(urlparse(start).query)["state"][0]
        assert parse_qs(urlparse(start).query)["code_challenge_method"] == ["S256"]
        assert client.get("/api/accounts/gmail/callback?state=wrong&code=one", follow_redirects=False).headers["location"].endswith("connection=failed")
        callback = client.get(f"/api/accounts/gmail/callback?state={state}&code=one", follow_redirects=False)
        assert callback.status_code == 303
        assert callback.headers["location"].endswith("connection=connected")
        account = client.get("/api/accounts").json()["accounts"][0]
        assert account["email"] == "owner@example.com"
        assert client.get("/api/onboarding").json()["ready"] is False
        assert client.put(f"/api/accounts/{account['id']}/sync-preferences", json={"history_months": 12, "interval_hours": 24, "include_sent": True}).status_code == 200
        for _ in range(40):
            if client.get(f"/api/accounts/{account['id']}/sync").json()["job"]["status"] == "complete":
                break
            time.sleep(0.025)
        else:
            raise AssertionError("The mailbox import did not complete")
        assert client.get("/api/onboarding").json()["ready"] is True
        sources, cards = main.assistant.context_for("insurance renewal")
        assert [source.title for source in sources] == ["Insurance renewal"]
        assert cards == []  # Retrieval itself does not invent cards.
        actions = client.get("/api/actions").json()
        assert len(actions) == 1
        assert actions[0]["source_refs"][0]["source_id"] == f"{account['id']}:gmail-1"
        assert actions[0]["status"] == "pending"
        assert client.delete(f"/api/accounts/{account['id']}").status_code == 204
        assert client.get("/api/onboarding").json()["ready"] is False
        assert repository.search_mail_sources("insurance") == []
        assert client.get("/api/actions").json() == []
        assert main.vault.get(f"account:{account['id']}") is None


def test_foreign_origin_cannot_write_profile(tmp_path: Path) -> None:
    main.repository = Repository(tmp_path / "api.db")
    with TestClient(main.app) as client:
        response = client.put("/api/profile", headers={"Origin": "https://unrelated.example"}, json={
            "first_name": "Asha", "last_name": "Rao", "age": 29, "phone_number": "+91 98765 43210", "gender": "woman", "time_zone": "Asia/Kolkata"})
        assert response.status_code == 403
        assert main.repository.get_profile() is None


def test_outlook_connection_and_import(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    main.repository = repository
    main.vault = CredentialVault(tmp_path)
    main.assistant = AssistantService(repository, main.settings)

    def provider(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "ms-access", "refresh_token": "ms-refresh"})
        if path == "/v1.0/me":
            return httpx.Response(200, json={"mail": "owner@outlook.com", "displayName": "Asha Rao"})
        if path == "/v1.0/me/messages":
            return httpx.Response(200, json={"value": []})
        if path.endswith("/mailFolders/inbox/messages"):
            return httpx.Response(200, json={"value": [{"id": "ms-1", "subject": "Project update", "bodyPreview": "Please send the report tomorrow.",
                "from": {"emailAddress": {"address": "manager@example.com"}}, "receivedDateTime": "2026-10-01T08:30:00Z"}]})
        raise AssertionError(f"Unexpected provider request: {request.url}")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))
    with TestClient(main.app) as client:
        client.put("/api/profile", json={"first_name": "Asha", "last_name": "Rao", "age": 29, "phone_number": "+91 98765 43210", "gender": "woman", "time_zone": "Asia/Kolkata"})
        assert client.post("/api/accounts/outlook/client", json={"client_id": "11111111-2222-3333-4444-555555555555"}).status_code == 200
        start = client.post("/api/accounts/outlook/start").json()["authorization_url"]
        state = parse_qs(urlparse(start).query)["state"][0]
        assert client.get(f"/api/accounts/outlook/callback?state={state}&code=one", follow_redirects=False).status_code == 303
        account = client.get("/api/accounts").json()["accounts"][0]
        assert client.put(f"/api/accounts/{account['id']}/sync-preferences", json={"history_months": 6, "interval_hours": 6, "include_sent": False}).status_code == 200
        for _ in range(40):
            if client.get(f"/api/accounts/{account['id']}/sync").json()["job"]["status"] == "complete":
                break
            time.sleep(0.025)
        else:
            raise AssertionError("Outlook import did not complete")
        sources, _ = main.assistant.context_for("project update")
        assert [(source.source_type, source.title, source.account_label) for source in sources] == [("email", "Project update", "Outlook / owner@outlook.com")]


def test_gmail_import_resumes_after_page_failure(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 12, 24, True)
    connector = ConnectorService(repository, CredentialVault(tmp_path))

    async def token(_account):
        return "access"

    monkeypatch.setattr(connector, "access_token", token)
    second_page_fails = True

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal second_page_fails
        if request.url.path.endswith("/messages"):
            if request.url.params.get("pageToken") == "page-2":
                if second_page_fails:
                    second_page_fails = False
                    return httpx.Response(503)
                return httpx.Response(200, json={"messages": [{"id": "mail-2"}]})
            return httpx.Response(200, json={"messages": [{"id": "mail-1"}], "nextPageToken": "page-2"})
        if request.url.path.endswith("/messages/mail-1") or request.url.path.endswith("/messages/mail-2"):
            message_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"id": message_id, "internalDate": "1790870400000", "snippet": "A unique message.",
                "payload": {"headers": [{"name": "Subject", "value": message_id}]}})
        raise AssertionError(f"Unexpected request: {request.url}")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))
    sync = MailSync(repository, connector)
    asyncio.run(sync.run(account["id"]))
    failed = repository.get_sync_job(account["id"])
    assert failed["status"] == "failed"
    assert failed["page_token"] == "page-2"
    assert failed["processed_count"] == 1
    asyncio.run(sync.run(account["id"]))
    done = repository.get_sync_job(account["id"])
    assert done["status"] == "complete"
    assert done["processed_count"] == 2
    assert {item["message_id"] for item in repository.search_mail_sources("")} == {"mail-1", "mail-2"}


def test_workspace_opens_only_after_first_import(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    repository.save_profile({"first_name": "Asha", "last_name": "Rao", "age": 29,
        "phone_number": "+91 98765 43210", "gender": "woman", "time_zone": "Asia/Kolkata"})
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 12, 24, True)
    assert repository.onboarding_status()["ready"] is False
    repository.start_sync_job(account["id"])
    assert repository.onboarding_status()["ready"] is False
    repository.update_sync_job(account["id"], "complete")
    assert repository.onboarding_status()["ready"] is True
    repository.upsert_mail_source(account["id"], "gmail", "old-message", "Older mail", "A message", "2025-01-01T00:00:00Z", "sender@example.com", "inbox")
    repository.reset_sync_job(account["id"])
    assert repository.onboarding_status()["ready"] is False
    assert repository.search_mail_sources("") == []
    assert repository.get_account(account["id"])["last_synced_at"] is None
