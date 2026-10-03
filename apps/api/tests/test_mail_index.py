import base64
import asyncio

import httpx

from app.mail_index import normalize_gmail_message
from app.mail_vectors import MailVectorIndex
from app.mail_sync import MailSync
from app.repository import Repository


def _message(identifier, epoch_ms, sender, subject, body, *, thread="thread-1", labels=None, attachment=False):
    parts = [{"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()}}]
    if attachment:
        parts.append({"mimeType": "application/pdf", "filename": "receipt.pdf", "body": {"attachmentId": "a1", "size": 123}})
    return {"id": identifier, "threadId": thread, "internalDate": str(epoch_ms), "labelIds": labels or ["INBOX"],
            "payload": {"mimeType": "multipart/mixed", "headers": [
                {"name": "From", "value": sender}, {"name": "To", "value": "Owner <owner@example.com>"},
                {"name": "Subject", "value": subject}, {"name": "Message-ID", "value": f"<{identifier}@example.com>"}], "parts": parts}}


def test_normalize_gmail_message_keeps_metadata_and_complete_body():
    raw = _message("m1", 1780000000000, "BookMyShow <tickets@bookmyshow.com>", "Your tickets", "A" * 4000, attachment=True)
    item = normalize_gmail_message(raw, "account", "owner@example.com")
    assert item["sender_address"] == "tickets@bookmyshow.com"
    assert item["direction"] == "received"
    assert item["thread_id"] == "thread-1"
    assert item["rfc_message_id"] == "<m1@example.com>"
    assert item["to_json"] == ["owner@example.com"]
    assert len(item["body_text"]) == 4000
    assert item["attachments_json"][0]["name"] == "receipt.pdf"


def test_html_body_used_when_plain_part_is_empty():
    raw = _message("m1", 1780000000000, "Sender <a@example.com>", "HTML", "")
    raw["payload"]["parts"].append({"mimeType": "text/html", "body": {
        "data": base64.urlsafe_b64encode(b"<p>Important <b>details</b></p><script>ignore()</script>").decode()}})
    item = normalize_gmail_message(raw, "account", "owner@example.com")
    assert "Important details" in item["body_text"]
    assert "ignore" not in item["body_text"]


def test_latest_sender_and_full_text_search(tmp_path):
    repository = Repository(tmp_path / "mail.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    records = [
        _message("m1", 1780000000000, "BookMyShow <tickets@bookmyshow.com>", "Tickets", "Your seats are B12 and B13.", attachment=True),
        _message("m2", 1780001000000, "BookMyShow <tickets@bookmyshow.com>", "Reminder", "Your movie starts tonight."),
        _message("m3", 1780002000000, "Friend <friend@example.com>", "Weekend", "Let's get coffee."),
    ]
    for raw in records:
        repository.upsert_mail_message(normalize_gmail_message(raw, account["id"], account["email"]))
    assert repository.search_mail_messages("latest received", direction="received", latest=True, limit=1)[0]["message_id"] == "m3"
    assert [item["message_id"] for item in repository.search_mail_messages("latest from book my show", sender="book my show", latest=True)] == ["m2", "m1"]
    result = repository.search_mail_messages("seats B12", sender="bookmyshow")
    assert result[0]["message_id"] == "m1"
    assert result[0]["thread_count"] == 3
    repository.upsert_mail_message(normalize_gmail_message(_message("m1", 1780000000000, "BookMyShow <tickets@bookmyshow.com>", "Tickets", "Updated seat C9."), account["id"], account["email"]))
    assert repository.search_mail_messages("B12") == []
    assert repository.search_mail_messages("C9")[0]["message_id"] == "m1"
    assert repository.mail_pipeline_counts(account["id"], "test-embed") == {
        "searchable_messages": 3, "embedded_messages": 0, "pending_embedding_chunks": 3,
        "imported_messages": 0, "processed_messages": 0, "discovered_messages": 0}


def test_vector_index_batches_chunks_and_resolves_to_live_messages(tmp_path, monkeypatch):
    repository = Repository(tmp_path / "mail.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.upsert_mail_message(normalize_gmail_message(
        _message("m1", 1780000000000, "Friend <friend@example.com>", "Flight", "The plane departs tomorrow."),
        account["id"], account["email"]))
    def provider(request):
        inputs = request.read().decode()
        if "input" not in inputs:
            raise AssertionError("Missing embedding input")
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0, 0.0]]})
    async_client = httpx.AsyncClient
    sync_client = httpx.Client
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: async_client(transport=httpx.MockTransport(provider), **kwargs))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: sync_client(transport=httpx.MockTransport(provider), **kwargs))
    index = MailVectorIndex(repository, tmp_path / "vectors", "http://ollama.test", "test-embed")
    assert asyncio.run(index.index_batch()) == 1
    assert asyncio.run(index.index_batch()) == 0
    ids = index.search("departure")
    assert repository.mail_messages_for_chunks(ids)[0]["message_id"] == "m1"
    repository.upsert_mail_message(normalize_gmail_message(
        _message("m2", 1780001000000, "Friend <friend@example.com>", "Arrival", "The train arrives today."),
        account["id"], account["email"]))
    assert asyncio.run(index.index_batch()) == 1
    assert len(index.search("arrival")) == 2
    repository.delete_mail_message(account["id"], "m1")
    assert repository.mail_messages_for_chunks(ids) == []
    index.remove_account(account["id"])
    assert index.search("arrival") == []


def test_full_scan_reconciliation_removes_deleted_mail(tmp_path):
    repository = Repository(tmp_path / "mail.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    for identifier in ("keep", "gone"):
        item = normalize_gmail_message(_message(identifier, 1780000000000, "Sender <a@example.com>", identifier, "Text"),
                                       account["id"], account["email"])
        repository.upsert_mail_message(item, "first-scan")
    repository.upsert_mail_message(normalize_gmail_message(
        _message("keep", 1780000000000, "Sender <a@example.com>", "keep", "Text"), account["id"], account["email"]), "second-scan")
    assert repository.reconcile_full_gmail_scan(account["id"], "second-scan", "2026-01-01T00:00:00+00:00", True) == 1
    assert [item["message_id"] for item in repository.search_mail_messages("mail", latest=True)] == ["keep"]


def test_gmail_detail_fetch_is_bounded_and_overlaps_requests(tmp_path):
    repository = Repository(tmp_path / "mail.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    sync = MailSync(repository, None)
    active = 0
    peak = 0

    async def provider(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.4)
        active -= 1
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1]})

    async def fetch():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            semaphore = asyncio.Semaphore(4)
            return await asyncio.gather(*(sync._gmail_detail(client, account, f"m{i}", {}, semaphore) for i in range(6)))

    result = asyncio.run(fetch())
    assert [item["id"] for item in result] == [f"m{i}" for i in range(6)]
    assert 1 < peak <= 4
