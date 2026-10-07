import asyncio
from pathlib import Path

from app.action_intelligence import ActionIntelligence, ChatCommand, MailDecision, MailEvent
from app.action_presentation import action_priority, action_title
from app.config import Settings
from app.repository import Repository


def setup(tmp_path: Path):
    repository = Repository(tmp_path / "actions.db")
    repository.initialize()
    account = repository.upsert_account("gmail", "owner@example.com", "Owner")
    repository.save_sync_preferences(account["id"], 12, 24, True)
    repository.start_sync_job(account["id"])
    repository.update_sync_job(account["id"], "complete")
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "actions.db", ollama_base_url="http://localhost:11434",
                        chat_model="test", llm_temperature=0, ollama_timeout_seconds=5, demo_mode=False)
    return repository, account, ActionIntelligence(repository, settings)


def add_mail(repository, account, message_id, subject, body, sent_at):
    repository.upsert_mail_source(account["id"], "gmail", message_id, subject, body, sent_at,
                                  "billing@example.com", "inbox")


def test_overdue_card_is_updated_by_later_payment_without_duplicate(tmp_path: Path, monkeypatch):
    repository, account, service = setup(tmp_path)
    add_mail(repository, account, "bill", "Credit card bill", "Your January bill of $120 is due January 1, 2026.",
             "2025-12-20T12:00:00+00:00")
    add_mail(repository, account, "paid", "Credit card payment", "Your January bill of $120 was paid January 10, 2026.",
             "2026-01-10T12:00:00+00:00")
    assert [job["message_id"] for job in repository.pending_mail_actions()] == ["bill", "paid"]

    async def fake_model(_system, user, _schema):
        if '"message_id"' in user:
            raise AssertionError("Unexpected payload")
        if "was paid" in user:
            candidates = repository.mail_action_candidates(account["id"], "Credit card payment")
            return MailDecision(events=[MailEvent(operation="complete", target_id=candidates[0]["id"],
                title="January credit card bill", description="The $120 January bill was paid on January 10, 2026.",
                due_date="2026-01-10", priority="low", confidence=0.95, evidence="was paid January 10, 2026")])
        return MailDecision(events=[MailEvent(operation="create", title="Pay January credit card bill",
            description="Pay the $120 January bill.", due_date="2026-01-01", priority="high", confidence=0.95,
            evidence="due January 1, 2026")])

    monkeypatch.setattr(service, "_structured", fake_model)
    first = asyncio.run(service.process_one(repository.pending_mail_actions()[0]))[0]
    assert first["due_at"].startswith("2026-01-01")
    assert first["status"] == "pending"  # UI derives Past due from the original date.
    second = asyncio.run(service.process_one(repository.pending_mail_actions()[0]))[0]
    assert second["id"] == first["id"]
    assert second["status"] == "completed"
    assert second["due_at"] == first["due_at"]
    assert len(second["source_refs"]) == 2
    details = repository.action_details(first["id"])
    assert [item["event_type"] for item in details["activity"]] == ["mail_created", "mail_completed"]
    assert details["activity"][-1]["source_id"] == f"{account['id']}:paid"
    assert [mail["title"] for mail in details["mails"]] == ["Credit card bill", "Credit card payment"]
    assert len(repository.list_actions()) == 1
    assert repository.pending_mail_actions() == []


def test_model_cannot_update_unknown_card_or_claim_unsupported_evidence(tmp_path: Path, monkeypatch):
    repository, account, service = setup(tmp_path)
    add_mail(repository, account, "one", "Newsletter", "Please review the weekly news.", "2026-01-01T00:00:00+00:00")

    async def fake_model(*_args):
        return MailDecision(events=[MailEvent(operation="complete", target_id="action_mail_invented",
            title="Paid bill", description="A payment was made.", confidence=0.99, evidence="payment was made"),
            MailEvent(operation="create", title="Fake action", description="Do an invented thing.",
                confidence=0.99, evidence="invented thing")])

    monkeypatch.setattr(service, "_structured", fake_model)
    assert asyncio.run(service.process_one(repository.pending_mail_actions()[0])) == []
    assert repository.list_actions() == []
    assert repository.pending_mail_actions() == []


def test_explicit_bill_and_payment_fast_path(tmp_path: Path, monkeypatch):
    repository, account, service = setup(tmp_path)
    add_mail(repository, account, "bill", "Acme Visa bill", "Your Acme Visa bill of $120 is due January 1, 2026.",
             "2025-12-20T12:00:00+00:00")
    add_mail(repository, account, "paid", "Acme Visa payment", "Your Acme Visa bill of $120 was paid January 10, 2026.",
             "2026-01-10T12:00:00+00:00")

    async def should_not_call_model(*_args):
        raise AssertionError("Explicit bill flow should not need a model request")

    monkeypatch.setattr(service, "_structured", should_not_call_model)
    first = asyncio.run(service.process_one(repository.pending_mail_actions()[0]))[0]
    second = asyncio.run(service.process_one(repository.pending_mail_actions()[0]))[0]
    assert second["id"] == first["id"]
    assert second["status"] == "completed"
    assert second["due_at"] == first["due_at"]
    assert len(repository.list_actions()) == 1


def test_chat_edit_accept_and_delete(tmp_path: Path, monkeypatch):
    from app import main

    repository, _account, service = setup(tmp_path)
    monkeypatch.setattr(main, "repository", repository)
    monkeypatch.setattr(main, "action_intelligence", service)
    decisions = iter([
        ChatCommand(operation="create", title="Renew passport", description="Book an appointment"),
        ChatCommand(operation="edit", target_id="placeholder"),
        ChatCommand(operation="accept", target_id="placeholder"),
        ChatCommand(operation="delete", target_id="placeholder"),
    ])

    async def fake_command(_message):
        command = next(decisions)
        if command.target_id == "placeholder":
            command.target_id = repository.list_actions()[0]["id"]
        return command

    monkeypatch.setattr(service, "chat_command", fake_command)
    created = asyncio.run(main.handle_action_chat("Create an action card to renew my passport by January 3, 2027"))[1][0]
    assert created.due_at.startswith("2027-01-03")
    edited = asyncio.run(main.handle_action_chat("Edit the passport action card priority to urgent"))[1][0]
    assert edited.priority == "urgent"
    accepted = asyncio.run(main.handle_action_chat("Accept the passport action card"))[1][0]
    assert accepted.status == "completed"
    assert repository.list_reminders()[0]["action_id"] == created.id
    repository.edit_action(created.id, {"status": "pending"})
    repository.execute_local_reminder(created.id)
    assert len(repository.list_reminders()) == 1
    asyncio.run(main.handle_action_chat("Delete the passport action card"))
    assert repository.list_actions() == []


def test_priority_and_title_policy():
    assert action_title("Sharing dining experience") == "Share dining experience"
    assert action_priority("Share dining experience on EazyDiner", "Leave an optional review", None) == "low"
    assert action_priority("Upload bill for EazyPoints", "Earn loyalty points", "2026-01-01T00:00:00+00:00", "urgent") == "low"
    assert action_priority("Refer friends for tax filing", "Earn rewards", "2026-01-01T00:00:00+00:00", "urgent") == "low"
    assert action_priority("File ITR", "Submit income tax return", "2026-01-01T00:00:00+00:00") == "high"
    assert action_priority("Complete application", "Submit by the deadline", "2026-01-01T00:00:00+00:00", "urgent") == "high"
    assert action_priority("Read newsletter", "Maybe read later", None) == "medium"


def test_decision_comments_are_saved_in_card_history(tmp_path: Path):
    repository, account, service = setup(tmp_path)
    add_mail(repository, account, "bill", "Acme Visa bill", "Your Acme Visa bill of $120 is due January 1, 2026.",
             "2025-12-20T12:00:00+00:00")
    card = asyncio.run(service.process_one(repository.pending_mail_actions()[0]))[0]
    approved, _ = repository.execute_local_reminder(card["id"], "Paid from another account")
    assert approved["completion_origin"] == "reminder"
    details = repository.action_details(card["id"])
    assert details["activity"][-1]["event_type"] == "approved"
    assert details["activity"][-1]["comment"] == "Paid from another account"
    assert details["mails"][0]["body"].startswith("Your Acme Visa")
    repository.edit_action(card["id"], {"status": "pending"})
    repository.decide_action(card["id"], "dismissed", "No longer needed")
    assert repository.action_details(card["id"])["activity"][-1]["comment"] == "No longer needed"
