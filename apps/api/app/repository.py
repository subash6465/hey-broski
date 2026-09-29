from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def document_chunks(text: str, size: int = 1000, overlap: int = 120) -> list[str]:
    """Split extracted text at word boundaries with a little context overlap."""
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        if current and len(" ".join(current)) + len(word) + 1 > size:
            chunks.append(" ".join(current))
            trailing: list[str] = []
            for previous in reversed(current):
                if len(" ".join(trailing)) + len(previous) + 1 > overlap:
                    break
                trailing.insert(0, previous)
            current = trailing
        current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


class Repository:
    """Small SQLite boundary. SQL stays here so services remain easy to test."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = Lock()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
        CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL, card_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, due_at TEXT, confidence REAL NOT NULL, sources TEXT NOT NULL, proposed_action TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status, created_at);
        CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS document_chunks (document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, chunk_index INTEGER NOT NULL, content TEXT NOT NULL, PRIMARY KEY(document_id, chunk_index));
        CREATE TABLE IF NOT EXISTS reminders (id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE REFERENCES actions(id) ON DELETE CASCADE, title TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, entity_id TEXT, details TEXT NOT NULL, created_at TEXT NOT NULL);
        """
        with self._lock, self.connect() as connection:
            connection.executescript(schema)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
            for name, declaration in (
                ("turn_id", "TEXT"),
                ("updated_at", "TEXT"),
                ("response_time_ms", "INTEGER"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE messages ADD COLUMN {name} {declaration}")
            connection.execute("UPDATE messages SET updated_at = created_at WHERE updated_at IS NULL")
            # Existing vault files are indexed without requiring users to re-upload.
            missing = connection.execute("""SELECT d.id, d.extracted_text FROM documents d
                WHERE NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id)""").fetchall()
            for document in missing:
                self._insert_chunks(connection, document["id"], document["extracted_text"])
            # Link legacy user/assistant rows by a shared turn ID.
            sessions = connection.execute("SELECT id FROM sessions").fetchall()
            for session in sessions:
                pending_turn = None
                rows = connection.execute("SELECT id, role FROM messages WHERE session_id = ? AND turn_id IS NULL ORDER BY created_at, rowid", (session["id"],)).fetchall()
                for row in rows:
                    if row["role"] == "user" or pending_turn is None:
                        pending_turn = f"turn_{uuid4().hex}"
                    connection.execute("UPDATE messages SET turn_id = ? WHERE id = ?", (pending_turn, row["id"]))
                    if row["role"] == "assistant":
                        pending_turn = None

    @staticmethod
    def _insert_chunks(connection: sqlite3.Connection, document_id: str, text: str) -> None:
        connection.executemany(
            "INSERT INTO document_chunks VALUES (?, ?, ?)",
            [(document_id, index, chunk) for index, chunk in enumerate(document_chunks(text))],
        )

    def create_session(self) -> dict[str, str]:
        session_id, timestamp = f"session_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (session_id, "New conversation", timestamp, timestamp))
        return {"session_id": session_id, "title": "New conversation", "created_at": timestamp}

    def session_exists(self, session_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone() is not None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""SELECT id AS session_id, title, created_at, updated_at FROM sessions
                WHERE EXISTS (SELECT 1 FROM messages WHERE messages.session_id = sessions.id)
                ORDER BY updated_at DESC""").fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._lock, self.connect() as connection:
            if not connection.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone():
                return False
            message_ids = {row["id"] for row in connection.execute("SELECT id FROM messages WHERE session_id = ?", (session_id,))}
            action_ids = {row["id"] for row in connection.execute("SELECT id FROM actions WHERE session_id = ?", (session_id,))}
            self._delete_audit_refs(connection, message_ids | action_ids | {session_id}, session_id)
            connection.execute("DELETE FROM actions WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._remove_action_cards(connection, action_ids)
        return True

    @staticmethod
    def _delete_audit_refs(connection: sqlite3.Connection, entity_ids: set[str], session_id: str | None = None) -> None:
        for row in connection.execute("SELECT id, entity_id, details FROM audit_log"):
            details = json.loads(row["details"])
            if row["entity_id"] in entity_ids or (session_id and details.get("session_id") == session_id):
                connection.execute("DELETE FROM audit_log WHERE id = ?", (row["id"],))

    @staticmethod
    def _remove_action_cards(connection: sqlite3.Connection, action_ids: set[str]) -> None:
        if not action_ids:
            return
        for row in connection.execute("SELECT id, metadata FROM messages"):
            metadata = json.loads(row["metadata"])
            cards = metadata.get("action_cards", [])
            kept = [card for card in cards if card.get("id") not in action_ids]
            if len(kept) != len(cards):
                metadata["action_cards"] = kept
                connection.execute("UPDATE messages SET metadata = ? WHERE id = ?", (json.dumps(metadata), row["id"]))

    def add_turn(self, session_id: str, question: str, answer: str, metadata: dict[str, Any], response_time_ms: int) -> tuple[str, str, str]:
        turn_id, user_id, answer_id, timestamp = (f"turn_{uuid4().hex}", f"msg_{uuid4().hex}", f"msg_{uuid4().hex}", now_iso())
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO messages (id, session_id, role, content, metadata, created_at, turn_id, updated_at) VALUES (?, ?, 'user', ?, '{}', ?, ?, ?)",
                (user_id, session_id, question, timestamp, turn_id, timestamp),
            )
            connection.execute(
                "INSERT INTO messages (id, session_id, role, content, metadata, created_at, turn_id, updated_at, response_time_ms) VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?)",
                (answer_id, session_id, answer, json.dumps(metadata), timestamp, turn_id, timestamp, response_time_ms),
            )
            connection.execute(
                "UPDATE sessions SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, updated_at = ? WHERE id = ?",
                (question[:60], timestamp, session_id),
            )
        return turn_id, user_id, answer_id

    def add_message(self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
        message_id, timestamp = f"msg_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO messages (id, session_id, role, content, metadata, created_at, turn_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (message_id, session_id, role, content, json.dumps(metadata or {}), timestamp, f"turn_{uuid4().hex}", timestamp))
            if role == "user":
                connection.execute("UPDATE sessions SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, updated_at = ? WHERE id = ?", (content[:60], timestamp, session_id))
            else:
                connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (timestamp, session_id))
        return message_id

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id, role, content, metadata, created_at, updated_at, turn_id, response_time_ms FROM messages WHERE session_id = ? ORDER BY created_at, rowid", (session_id,)).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]

    def upsert_action(self, action: dict[str, Any]) -> None:
        timestamp = now_iso()
        values = (action["id"], action.get("session_id"), action["card_type"], action["title"], action["description"], action["priority"], action["status"], action.get("due_at"), action["confidence"], json.dumps(action["sources"]), json.dumps(action.get("proposed_action")), timestamp, timestamp)
        with self._lock, self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)

    def list_actions(self, status: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM actions", ()
        if status:
            query, params = query + " WHERE status = ?", (status,)
        with self.connect() as connection:
            rows = connection.execute(query + " ORDER BY created_at DESC", params).fetchall()
        return [self._decode_action(row) for row in rows]

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
        return self._decode_action(row) if row else None

    def decide_action(self, action_id: str, new_status: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE actions SET status = ?, updated_at = ? WHERE id = ? AND status = 'pending'", (new_status, now_iso(), action_id))
        return self.get_action(action_id)

    def execute_local_reminder(self, action_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Create the local side effect and status update in one transaction."""
        reminder_id, timestamp = f"reminder_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            action = connection.execute("SELECT * FROM actions WHERE id = ? AND status = 'pending'", (action_id,)).fetchone()
            if not action:
                return self.get_action(action_id), {"executed": False}
            connection.execute(
                "INSERT INTO reminders VALUES (?, ?, ?, ?, ?)",
                (reminder_id, action_id, action["title"], action["due_at"], timestamp),
            )
            connection.execute(
                "UPDATE actions SET status = 'completed', updated_at = ? WHERE id = ?",
                (timestamp, action_id),
            )
        return self.get_action(action_id), {"executed": True, "reminder_id": reminder_id}

    def list_reminders(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM reminders ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _decode_action(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["source_refs"] = json.loads(item.pop("sources"))
        item["proposed_action"] = json.loads(item["proposed_action"]) if item["proposed_action"] else None
        for key in ("session_id", "created_at", "updated_at"):
            item.pop(key, None)
        return item

    def add_document(self, filename: str, content_type: str, size_bytes: int, text: str) -> dict[str, Any]:
        document_id, timestamp = f"doc_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)", (document_id, filename, content_type, size_bytes, text, timestamp))
            self._insert_chunks(connection, document_id, text)
        return {"id": document_id, "filename": filename, "content_type": content_type, "size_bytes": size_bytes, "created_at": timestamp, "preview": text[:240]}

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id, filename, content_type, size_bytes, created_at, substr(extracted_text, 1, 240) AS preview FROM documents ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with self._lock, self.connect() as connection:
            if not connection.execute("SELECT 1 FROM documents WHERE id = ?", (document_id,)).fetchone():
                return False
            # The foreign key cascades to document_chunks. Saved conversations
            # retain their historical source snapshots and answers.
            self._delete_audit_refs(connection, {document_id})
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return True

    def search_documents(self, terms: list[str], limit: int = 5) -> list[dict[str, Any]]:
        if not terms:
            return []
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        scored = []
        for row in rows:
            haystack = f"{row['filename']} {row['extracted_text']}".lower()
            score = sum(term in haystack for term in terms)
            if score:
                scored.append((score, dict(row)))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

    def search_document_chunks(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        stopwords = {"about", "after", "before", "could", "does", "document", "documents", "from", "have", "into", "please", "show", "summarize", "tell", "that", "their", "there", "these", "this", "what", "when", "where", "which", "with", "would", "your"}
        terms = set(re.findall(r"[a-z0-9]{3,}", query.lower())) - stopwords
        with self.connect() as connection:
            rows = connection.execute("""SELECT c.document_id, c.chunk_index, c.content, d.filename, d.created_at
                FROM document_chunks c JOIN documents d ON d.id = c.document_id
                ORDER BY d.created_at DESC, c.chunk_index""").fetchall()
        scored = []
        for row in rows:
            filename = row["filename"].lower()
            content = row["content"].lower()
            matched = sum(2 if term in filename else 0 for term in terms) + sum(min(content.count(term), 3) for term in terms)
            if matched:
                scored.append((matched, dict(row)))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if not scored and len({row["document_id"] for row in rows}) == 1:
            return [dict(row) for row in rows[:limit]]
        return [row for _, row in scored[:limit]]

    def audit(self, event_type: str, entity_id: str | None, details: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO audit_log VALUES (?, ?, ?, ?, ?)", (f"audit_{uuid4().hex}", event_type, entity_id, json.dumps(details), now_iso()))

    def list_audit(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100").fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
