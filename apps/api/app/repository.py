from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """Small SQLite boundary. SQL stays here so services remain easy to test."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = Lock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
        CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL, card_type TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, due_at TEXT, confidence REAL NOT NULL, sources TEXT NOT NULL, proposed_action TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status, created_at);
        CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reminders (id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE REFERENCES actions(id) ON DELETE CASCADE, title TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, entity_id TEXT, details TEXT NOT NULL, created_at TEXT NOT NULL);
        """
        with self._lock, self.connect() as connection:
            connection.executescript(schema)

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
            rows = connection.execute("SELECT id AS session_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 50").fetchall()
        return [dict(row) for row in rows]

    def add_message(self, session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
        message_id, timestamp = f"msg_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)", (message_id, session_id, role, content, json.dumps(metadata or {}), timestamp))
            if role == "user":
                connection.execute("UPDATE sessions SET title = CASE WHEN title = 'New conversation' THEN ? ELSE title END, updated_at = ? WHERE id = ?", (content[:60], timestamp, session_id))
            else:
                connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (timestamp, session_id))
        return message_id

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id, role, content, metadata, created_at FROM messages WHERE session_id = ? ORDER BY created_at", (session_id,)).fetchall()
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
        return {"id": document_id, "filename": filename, "content_type": content_type, "size_bytes": size_bytes, "created_at": timestamp, "preview": text[:240]}

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id, filename, content_type, size_bytes, created_at, substr(extracted_text, 1, 240) AS preview FROM documents ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

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

    def audit(self, event_type: str, entity_id: str | None, details: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO audit_log VALUES (?, ?, ?, ?, ?)", (f"audit_{uuid4().hex}", event_type, entity_id, json.dumps(details), now_iso()))

    def list_audit(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100").fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]
