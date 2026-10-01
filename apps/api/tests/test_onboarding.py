import time
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient

from app import main
from app.assistant import AssistantService
from app.credential_vault import CredentialVault
from app.connectors import ConnectorService
from app.mail_sync import MailSync
from app.repository import Repository
from app import repository as repository_module, schemas as profile_schemas
from zoneinfo import ZoneInfoNotFoundError


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
        profile = {"first_name": "Asha", "last_name": "Rao", "date_of_birth": "1997-05-12", "country_code": "+91", "phone_number": "9876543210", "gender": "female", "time_zone": "Asia/Kolkata"}
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
            "first_name": "Asha", "last_name": "Rao", "date_of_birth": "1997-05-12", "country_code": "+91", "phone_number": "9876543210", "gender": "female", "time_zone": "Asia/Kolkata"})
        assert response.status_code == 403
        assert main.repository.get_profile() is None


def test_google_desktop_json_accepts_google_issued_auth_uri(tmp_path: Path) -> None:
    main.repository = Repository(tmp_path / "api.db")
    main.vault = CredentialVault(tmp_path)
    with TestClient(main.app) as client:
        credentials = {"installed": {"client_id": "abc.apps.googleusercontent.com", "client_secret": "secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]}}
        assert client.post("/api/accounts/gmail/client", json={"credentials": credentials}).status_code == 200
        credentials["installed"]["auth_uri"] = "https://attacker.example/authorize"
        assert client.post("/api/accounts/gmail/client", json={"credentials": credentials}).status_code == 400


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
        client.put("/api/profile", json={"first_name": "Asha", "last_name": "Rao", "date_of_birth": "1997-05-12", "country_code": "+91", "phone_number": "9876543210", "gender": "female", "time_zone": "Asia/Kolkata"})
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
                    return httpx.Response(403, json={"error": {"message": "Daily limit exceeded", "errors": [{"reason": "dailyLimitExceeded"}]}})
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


def test_gmail_import_retries_rate_limit_and_checkpoints_each_message(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 24, 24, True)
    connector = ConnectorService(repository, CredentialVault(tmp_path))

    async def token(_account):
        return "access"

    async def no_delay(_seconds):
        return None

    monkeypatch.setattr(connector, "access_token", token)
    monkeypatch.setattr("app.mail_sync.asyncio.sleep", no_delay)
    requests = {"first": 0, "second": 0}
    fail_second = True

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal fail_second
        path = request.url.path
        if path.endswith("/messages"):
            return httpx.Response(200, json={"resultSizeEstimate": 2, "messages": [{"id": "mail-1"}, {"id": "mail-2"}]})
        if path.endswith("/messages/mail-1"):
            requests["first"] += 1
            if requests["first"] == 1:
                return httpx.Response(403, json={"error": {"message": "User Rate Limit Exceeded", "errors": [{"reason": "userRateLimitExceeded"}]}})
        elif path.endswith("/messages/mail-2"):
            requests["second"] += 1
            if fail_second:
                fail_second = False
                return httpx.Response(403, json={"error": {"message": "Daily Limit Exceeded", "errors": [{"reason": "dailyLimitExceeded"}]}})
        else:
            raise AssertionError(f"Unexpected request: {request.url}")
        return httpx.Response(200, json={"id": path.rsplit("/", 1)[-1], "internalDate": "1790870400000",
            "snippet": "A unique message.", "payload": {"headers": [{"name": "Subject", "value": "Test"}]}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))
    sync = MailSync(repository, connector)
    asyncio.run(sync.run(account["id"]))
    failed = repository.get_sync_job(account["id"])
    assert failed["status"] == "failed"
    assert failed["processed_count"] == 1
    assert failed["total_estimate"] == 2
    assert '"offset": 1' in failed["page_token"]
    asyncio.run(sync.run(account["id"]))
    done = repository.get_sync_job(account["id"])
    assert done["status"] == "complete"
    assert done["processed_count"] == 2
    assert requests == {"first": 2, "second": 2}  # Retry mail-1 in place; resume skips it later.


def test_gmail_skips_one_inaccessible_message_without_stopping_import(tmp_path: Path, monkeypatch) -> None:
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 3, 24, True)
    connector = ConnectorService(repository, CredentialVault(tmp_path))

    async def token(_account):
        return "access"

    monkeypatch.setattr(connector, "access_token", token)

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"resultSizeEstimate": 2, "messages": [{"id": "gone"}, {"id": "good"}]})
        if request.url.path.endswith("/messages/gone"):
            return httpx.Response(403, json={"error": {"message": "Message unavailable", "errors": [{"reason": "forbidden"}]}})
        return httpx.Response(200, json={"id": "good", "internalDate": "1790870400000", "snippet": "Good message",
            "payload": {"headers": [{"name": "Subject", "value": "Good"}]}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs))
    asyncio.run(MailSync(repository, connector).run(account["id"]))
    job = repository.get_sync_job(account["id"])
    assert job["status"] == "complete"
    assert job["processed_count"] == 1
    assert job["skipped_count"] == 1


def test_workspace_opens_when_import_is_configured(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    repository.save_profile({"first_name": "Asha", "last_name": "Rao", "date_of_birth": "1997-05-12",
        "country_code": "+91", "phone_number": "9876543210", "gender": "female", "time_zone": "Asia/Kolkata"})
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 12, 24, True)
    assert repository.onboarding_status()["ready"] is True
    repository.start_sync_job(account["id"])
    assert repository.onboarding_status()["ready"] is True
    repository.update_sync_job(account["id"], "complete")
    assert repository.onboarding_status()["ready"] is True
    repository.upsert_mail_source(account["id"], "gmail", "old-message", "Older mail", "A message", "2025-01-01T00:00:00Z", "sender@example.com", "inbox")
    repository.reset_sync_job(account["id"])
    assert repository.onboarding_status()["ready"] is True
    assert repository.search_mail_sources("") == []
    assert repository.get_account(account["id"])["last_synced_at"] is None


def test_existing_sync_job_schema_gains_progress_columns(tmp_path: Path) -> None:
    database = tmp_path / "api.db"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE sync_jobs (account_id TEXT PRIMARY KEY, status TEXT NOT NULL,
            processed_count INTEGER NOT NULL DEFAULT 0, page_token TEXT, started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, error TEXT)""")
    repository = Repository(database)
    repository.initialize()
    with repository.connect() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sync_jobs)")}
    assert {"total_estimate", "skipped_count"} <= columns


def test_existing_profile_migrates_and_age_comes_from_birth_date(tmp_path: Path) -> None:
    database = tmp_path / "api.db"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE owner_profile (id INTEGER PRIMARY KEY, first_name TEXT NOT NULL,
            last_name TEXT NOT NULL, age INTEGER NOT NULL, phone_number TEXT NOT NULL,
            gender TEXT NOT NULL, time_zone TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.execute("INSERT INTO owner_profile VALUES (1, 'Asha', 'Rao', 29, '+91 9876543210', 'woman', 'Asia/Kolkata', '2026-01-01')")
    repository = Repository(database)
    repository.initialize()
    assert repository.get_profile()["first_name"] == "Asha"
    assert repository.profile_complete() is False
    profile = repository.save_profile({"first_name": "Asha", "last_name": "Rao", "date_of_birth": "1997-05-12",
        "country_code": "+91", "phone_number": "9876543210", "gender": "self described", "time_zone": "Asia/Kolkata"})
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    expected_age = today.year - 1997 - ((today.month, today.day) < (5, 12))
    assert profile["age"] == expected_age
    assert profile["gender"] == "self described"
    assert repository.profile_complete() is True


def test_profile_rejects_future_birth_date_and_invalid_phone(tmp_path: Path) -> None:
    main.repository = Repository(tmp_path / "api.db")
    with TestClient(main.app) as client:
        profile = {"first_name": "Asha", "last_name": "Rao", "date_of_birth": "2999-01-01",
            "country_code": "+91", "phone_number": "9876543210", "gender": "female", "time_zone": "Asia/Kolkata"}
        assert client.put("/api/profile", json=profile).status_code == 422
        assert client.put("/api/profile", json={**profile, "date_of_birth": "1997-05-12", "country_code": "91"}).status_code == 422
        assert client.put("/api/profile", json={**profile, "date_of_birth": "1997-05-12", "phone_number": "98 765"}).status_code == 422


def test_profile_uses_machine_date_if_zone_database_is_missing(tmp_path: Path, monkeypatch) -> None:
    def missing_zone(_name: str):
        raise ZoneInfoNotFoundError("zone data unavailable")

    monkeypatch.setattr(profile_schemas, "ZoneInfo", missing_zone)
    monkeypatch.setattr(repository_module, "ZoneInfo", missing_zone)
    profile = profile_schemas.OwnerProfileInput.model_validate({"first_name": "Asha", "last_name": "Rao",
        "date_of_birth": "1997-05-12", "country_code": "+91", "phone_number": "9876543210",
        "gender": "female", "time_zone": "Asia/Calcutta"})
    repository = Repository(tmp_path / "api.db")
    repository.initialize()
    saved = repository.save_profile(profile.model_dump())
    assert saved["date_of_birth"] == "1997-05-12"
    assert repository.profile_complete() is True
