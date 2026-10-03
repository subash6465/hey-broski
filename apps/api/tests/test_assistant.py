from datetime import date
import asyncio
from pathlib import Path

from app.assistant import AssistantService
from app.config import Settings
from app.demo_data import DEMO_SOURCES
from app.repository import Repository
from app.mail_index import normalize_gmail_message


def service(tmp_path: Path) -> AssistantService:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    settings = Settings(tmp_path, tmp_path / "test.db", "http://127.0.0.1:1", "qwen3:4b-instruct", 0.2, 0.01, True)
    return AssistantService(repository, settings)


def test_renewal_query_is_grounded_and_actionable(tmp_path: Path) -> None:
    sources, actions = service(tmp_path).context_for("Show renewals and deadlines")

    assert {source.source_id for source in sources} == {
        "email-card-bill", "doc-headphones-warranty", "email-canva-renewal"
    }
    assert all(action.status == "pending" for action in actions)
    assert all(action.proposed_action["requires_approval"] for action in actions if action.proposed_action)


def test_follow_up_reuses_document_from_previous_question(tmp_path: Path) -> None:
    assistant = service(tmp_path)
    assistant.repository.add_document("smoke.txt", "text/plain", 55, "The meeting code is ORCHID-42. The project owner is Ada.")

    sources, _ = assistant.context_for("Who is the project owner?", "What is the code in smoke.txt?")

    assert sources
    assert all(source.source_type == "document" for source in sources)
    assert "Ada" in sources[0].snippet


def test_upcoming_demo_filter_excludes_expired_and_stale_items() -> None:
    today = date(2026, 9, 29)
    week_start = date(2026, 9, 28)

    assert not AssistantService._is_current_demo_source(DEMO_SOURCES[0], today, week_start)
    assert not AssistantService._is_current_demo_source(DEMO_SOURCES[1], today, week_start)
    assert AssistantService._is_current_demo_source(DEMO_SOURCES[2], today, week_start)


def test_latest_received_uses_metadata_without_model(tmp_path: Path) -> None:
    assistant = service(tmp_path)
    account = assistant.repository.upsert_account("gmail", "owner@example.com", "Owner")
    message = {"id": "last-1", "threadId": "thread-1", "internalDate": "1780000000000", "labelIds": ["INBOX"],
               "snippet": "Your ticket is confirmed.", "payload": {"headers": [
                   {"name": "From", "value": "Tickets <tickets@bookmyshow.com>"},
                   {"name": "Subject", "value": "Confirmed ticket"}]}}
    assistant.repository.upsert_mail_message(normalize_gmail_message(message, account["id"], account["email"]))
    sources, _ = assistant.context_for("Which is the latest mail I received?")
    assert len(sources) == 1
    assert sources[0].metadata["sender"] == "tickets@bookmyshow.com"
    assert "Confirmed ticket" in assistant._metadata_answer("Which is the latest mail I received?", sources)
    vendor, _ = assistant.context_for("Can you get me the details of the mails I received from book my show?")
    assert [item.source_id for item in vendor] == [sources[0].source_id]


def test_initial_import_qualifies_latest_and_blocks_complete_counts(tmp_path: Path) -> None:
    assistant = service(tmp_path)
    account = assistant.repository.upsert_account("gmail", "owner@example.com", "Owner")
    assistant.repository.save_sync_preferences(account["id"], 12, 24, True)
    assistant.repository.upsert_mail_message(normalize_gmail_message({
        "id": "partial", "threadId": "thread", "internalDate": "1780000000000", "labelIds": ["INBOX"],
        "snippet": "Your booking is confirmed.", "payload": {"headers": [
            {"name": "From", "value": "Tickets <tickets@example.com>"},
            {"name": "Subject", "value": "Booking"}]}}, account["id"], account["email"]))
    sources, _ = assistant.context_for("What is the latest mail I received?")
    latest, generated_by = asyncio.run(assistant.answer("What is the latest mail I received?", sources))
    assert generated_by == "metadata"
    assert "indexed so far" in latest
    count, generated_by = asyncio.run(assistant.answer("How many emails do I have?", sources))
    assert generated_by == "coverage"
    assert "initial import is incomplete" in count

    async def stream_count():
        return [event async for event in assistant.stream_answer("How many emails do I have?", sources)]

    events = asyncio.run(stream_count())
    assert events[-1]["generated_by"] == "coverage"
    assert events[-1]["content"] == count

    assistant.repository.start_sync_job(account["id"])
    assistant.repository.update_sync_job(account["id"], "complete", skipped=1)
    assistant.repository.mark_mail_index_backfilled(account["id"])
    incomplete_count, generated_by = asyncio.run(assistant.answer("How many emails do I have?", sources))
    assert generated_by == "coverage"
    assert "1 message was inaccessible" in incomplete_count
