import sqlite3
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


def test_document_fts_backfills_existing_chunks_and_removes_deleted_text(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL,
            content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE document_chunks (document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, content TEXT NOT NULL, PRIMARY KEY(document_id, chunk_index))""")
        connection.execute("INSERT INTO documents VALUES ('old','legacy.txt','text/plain',30,'The code is PINE-731','2026-01-01')")
        connection.execute("INSERT INTO document_chunks VALUES ('old',0,'The code is PINE-731')")
    repository = Repository(database)
    repository.initialize()
    assert repository.search_document_chunks("PINE-731")[0]["document_id"] == "old"
    assert repository.delete_document("old")
    assert repository.search_document_chunks("PINE-731") == []


def test_document_chunks_find_content_beyond_preview_and_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "test.db"
    repository = Repository(path)
    repository.initialize()
    document = repository.add_document(
        "policy.txt", "text/plain", 2500,
        ("General terms and conditions. " * 45) + "The refund period is exactly 37 days. " + ("Other clauses follow. " * 40),
    )

    matches = repository.search_document_chunks("What is the refund period in policy.txt?")
    assert matches
    assert matches[0]["document_id"] == document["id"]
    assert "37 days" in matches[0]["content"]

    repository.initialize()  # Migration/indexing must be idempotent.
    assert repository.search_document_chunks("refund period")[0]["document_id"] == document["id"]


def test_completed_turn_has_shared_id_and_response_metadata(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    session = repository.create_session()
    turn_id, user_id, answer_id = repository.add_turn(
        session["session_id"], "What is due?", "The bill is due. [Source 1]",
        {"sources": [{"source_id": "bill"}], "generated_by": "ollama"}, 1234,
    )

    messages = repository.list_messages(session["session_id"])
    assert [message["id"] for message in messages] == [user_id, answer_id]
    assert {message["turn_id"] for message in messages} == {turn_id}
    assert messages[1]["response_time_ms"] == 1234
    assert messages[1]["metadata"]["sources"][0]["source_id"] == "bill"
    assert all(message["updated_at"] for message in messages)
    assert repository.list_sessions()[0]["title"] == "What is due?"


def test_existing_messages_and_documents_are_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
            CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL);
            INSERT INTO sessions VALUES ('s1', 'Old chat', '2026-01-01', '2026-01-01');
            INSERT INTO messages VALUES ('u1', 's1', 'user', 'Tell me about policy.txt', '{}', '2026-01-01');
            INSERT INTO messages VALUES ('a1', 's1', 'assistant', 'The refund takes 37 days.', '{}', '2026-01-01');
            INSERT INTO documents VALUES ('d1', 'policy.txt', 'text/plain', 25, 'The refund takes 37 days.', '2026-01-01');
        """)

    repository = Repository(path)
    repository.initialize()
    messages = repository.list_messages("s1")
    assert [message["id"] for message in messages] == ["u1", "a1"]
    assert messages[0]["turn_id"] == messages[1]["turn_id"]
    assert repository.search_document_chunks("refund policy.txt")[0]["document_id"] == "d1"


def test_deleting_conversation_removes_related_database_rows(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    target = repository.create_session()["session_id"]
    other = repository.create_session()["session_id"]
    _, _, answer_id = repository.add_turn(target, "Secret question", "Secret answer", {}, 10)
    repository.add_turn(other, "Keep question", "Keep answer", {"action_cards": [{"id": "action_to_delete"}]}, 10)
    repository.upsert_action({
        "id": "action_to_delete", "session_id": target, "card_type": "reminder", "title": "Secret reminder",
        "description": "Secret description", "priority": "high", "status": "pending", "due_at": None,
        "confidence": 1.0, "sources": [], "proposed_action": None,
    })
    repository.execute_local_reminder("action_to_delete")
    repository.audit("chat.completed", answer_id, {"session_id": target})
    repository.audit("keep.event", other, {})

    assert repository.delete_session(target)
    assert not repository.delete_session(target)
    assert not repository.session_exists(target)
    assert repository.list_messages(target) == []
    assert repository.get_action("action_to_delete") is None
    assert repository.list_reminders() == []
    assert all(event["entity_id"] != answer_id for event in repository.list_audit())
    assert len(repository.list_messages(other)) == 2
    assert repository.list_messages(other)[1]["metadata"]["action_cards"] == []


def test_deleting_document_removes_index_but_preserves_history(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "test.db")
    repository.initialize()
    document = repository.add_document("secret.txt", "text/plain", 40, "The secret project code is ORCHID-42.")
    session = repository.create_session()["session_id"]
    source_id = f'{document["id"]}#part-1'
    _, _, answer_id = repository.add_turn(session, "What is the code?", "It is ORCHID-42.", {
        "sources": [{"source_id": source_id, "snippet": "The secret project code is ORCHID-42."}],
    }, 10)
    repository.add_turn(session, "Keep question", "Keep answer", {}, 10)
    repository.audit("document.uploaded", document["id"], {"filename": "secret.txt"})
    repository.audit("chat.completed", answer_id, {"session_id": session})
    repository.upsert_action({
        "id": "action_from_document", "session_id": session, "card_type": "reminder", "title": "Secret action",
        "description": "Secret description", "priority": "medium", "status": "pending", "due_at": None,
        "confidence": 1.0, "sources": [{"source_id": source_id}], "proposed_action": None,
    })
    repository.execute_local_reminder("action_from_document")

    assert repository.delete_document(document["id"])
    assert not repository.delete_document(document["id"])
    assert repository.list_documents() == []
    assert repository.search_document_chunks("ORCHID-42") == []
    assert [message["content"] for message in repository.list_messages(session)] == ["What is the code?", "It is ORCHID-42.", "Keep question", "Keep answer"]
    assert repository.list_messages(session)[1]["metadata"]["sources"][0]["source_id"] == source_id
    assert repository.list_sessions()[0]["title"] == "What is the code?"
    assert repository.get_action("action_from_document") is not None
    assert len(repository.list_reminders()) == 1
    assert all(event["entity_id"] != document["id"] for event in repository.list_audit())
    assert any(event["entity_id"] == answer_id for event in repository.list_audit())
    repository.initialize()
    assert repository.search_document_chunks("ORCHID-42") == []
    with repository.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (document["id"],)).fetchone()[0] == 0
