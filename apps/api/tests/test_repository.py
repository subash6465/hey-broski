from pathlib import Path

from app.repository import Repository


def test_session_messages_actions_and_audit(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    session = repository.create_session()
    message_id = repository.add_message(session["session_id"], "user", "What is due?")

    assert message_id.startswith("msg_")
    assert repository.list_sessions()[0]["title"] == "What is due?"
    assert repository.list_messages(session["session_id"])[0]["content"] == "What is due?"

    repository.audit("test.event", message_id, {"safe": True})
    assert repository.list_audit()[0]["details"] == {"safe": True}


def test_document_keyword_search(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    repository.add_document("policy.txt", "text/plain", 30, "Home insurance renews on 15 October")

    results = repository.search_documents(["insurance", "renewal"])

    assert len(results) == 1
    assert results[0]["filename"] == "policy.txt"
