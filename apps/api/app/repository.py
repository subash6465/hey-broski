from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_in_zone(zone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(zone_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.now().date()


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
        CREATE TABLE IF NOT EXISTS owner_profile (id INTEGER PRIMARY KEY CHECK (id = 1), first_name TEXT NOT NULL, last_name TEXT NOT NULL, age INTEGER NOT NULL, phone_number TEXT NOT NULL, gender TEXT NOT NULL, time_zone TEXT NOT NULL, updated_at TEXT NOT NULL, date_of_birth TEXT, country_code TEXT);
        CREATE TABLE IF NOT EXISTS connected_accounts (id TEXT PRIMARY KEY, provider TEXT NOT NULL, email TEXT NOT NULL, display_name TEXT NOT NULL, status TEXT NOT NULL, connected_at TEXT NOT NULL, last_synced_at TEXT, sync_error TEXT, UNIQUE(provider, email));
        CREATE TABLE IF NOT EXISTS oauth_attempts (state TEXT PRIMARY KEY, provider TEXT NOT NULL, code_verifier TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_preferences (account_id TEXT PRIMARY KEY REFERENCES connected_accounts(id) ON DELETE CASCADE, history_months INTEGER NOT NULL, interval_hours INTEGER NOT NULL, include_sent INTEGER NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mail_sources (provider TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES connected_accounts(id) ON DELETE CASCADE, message_id TEXT NOT NULL, title TEXT NOT NULL, snippet TEXT NOT NULL, sent_at TEXT NOT NULL, sender TEXT NOT NULL, folder TEXT NOT NULL, PRIMARY KEY(account_id, message_id));
        CREATE TABLE IF NOT EXISTS sync_jobs (account_id TEXT PRIMARY KEY REFERENCES connected_accounts(id) ON DELETE CASCADE, status TEXT NOT NULL, processed_count INTEGER NOT NULL DEFAULT 0, page_token TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT);
        CREATE INDEX IF NOT EXISTS idx_mail_sources_account_date ON mail_sources(account_id, sent_at);
        """
        with self._lock, self.connect() as connection:
            connection.executescript(schema)
            profile_columns = {row[1] for row in connection.execute("PRAGMA table_info(owner_profile)")}
            for name in ("date_of_birth", "country_code"):
                if name not in profile_columns:
                    connection.execute(f"ALTER TABLE owner_profile ADD COLUMN {name} TEXT")
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
        clauses = []
        if status:
            clauses.append("status = ?")
            params = (status,)
        if self.list_accounts():
            clauses.append("id NOT IN ('action_email-card-bill', 'action_email-manager-report', 'action_doc-headphones-warranty', 'action_event-design-review', 'action_email-canva-renewal')")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
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

    def get_profile(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM owner_profile WHERE id = 1").fetchone()
        if not row:
            return None
        profile = dict(row)
        if profile["date_of_birth"]:
            born = date.fromisoformat(profile["date_of_birth"])
            today = today_in_zone(profile["time_zone"])
            profile["age"] = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return profile

    def profile_complete(self) -> bool:
        profile = self.get_profile()
        return bool(profile and profile["date_of_birth"] and profile["country_code"])

    def save_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        born = profile["date_of_birth"]
        if isinstance(born, str):
            born = date.fromisoformat(born)
        today = today_in_zone(profile["time_zone"])
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO owner_profile
                (id, first_name, last_name, age, phone_number, gender, time_zone, updated_at, date_of_birth, country_code)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET first_name=excluded.first_name, last_name=excluded.last_name,
                age=excluded.age, phone_number=excluded.phone_number, gender=excluded.gender,
                time_zone=excluded.time_zone, updated_at=excluded.updated_at,
                date_of_birth=excluded.date_of_birth, country_code=excluded.country_code""",
                (profile["first_name"], profile["last_name"], age, profile["phone_number"], profile["gender"], profile["time_zone"], now_iso(), born.isoformat(), profile["country_code"]))
        return self.get_profile() or profile

    def create_oauth_attempt(self, state: str, provider: str, verifier: str, expires_at: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("INSERT INTO oauth_attempts VALUES (?, ?, ?, ?)", (state, provider, verifier, expires_at))

    def consume_oauth_attempt(self, state: str, provider: str) -> dict[str, Any] | None:
        with self._lock, self.connect() as connection:
            row = connection.execute("SELECT * FROM oauth_attempts WHERE state = ? AND provider = ?", (state, provider)).fetchone()
            if row:
                connection.execute("DELETE FROM oauth_attempts WHERE state = ?", (state,))
        return dict(row) if row and row["expires_at"] > now_iso() else None

    def upsert_account(self, provider: str, email: str, display_name: str) -> dict[str, Any]:
        account_id = f"{provider}_{uuid4().hex}"
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO connected_accounts (id, provider, email, display_name, status, connected_at)
                VALUES (?, ?, ?, ?, 'connected', ?) ON CONFLICT(provider, email) DO UPDATE SET
                display_name=excluded.display_name, status='connected', sync_error=NULL""",
                (account_id, provider, email.lower(), display_name, now_iso()))
            row = connection.execute("SELECT * FROM connected_accounts WHERE provider = ? AND email = ?", (provider, email.lower())).fetchone()
        return dict(row)

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM connected_accounts ORDER BY connected_at").fetchall()
        return [dict(row) for row in rows]

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM connected_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None

    def delete_account(self, account_id: str) -> bool:
        with self._lock, self.connect() as connection:
            related = {row["id"] for row in connection.execute("SELECT id, sources FROM actions")
                if any(source.get("source_id", "").startswith(f"{account_id}:") for source in json.loads(row["sources"]))}
            for action_id in related:
                connection.execute("DELETE FROM actions WHERE id=?", (action_id,))
            self._remove_action_cards(connection, related)
            return connection.execute("DELETE FROM connected_accounts WHERE id = ?", (account_id,)).rowcount > 0

    def save_sync_preferences(self, account_id: str, history_months: int, interval_hours: int, include_sent: bool) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO sync_preferences VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET history_months=excluded.history_months,
                interval_hours=excluded.interval_hours, include_sent=excluded.include_sent, updated_at=excluded.updated_at""",
                (account_id, history_months, interval_hours, int(include_sent), now_iso()))
        return self.get_sync_preferences(account_id) or {}

    def get_sync_preferences(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sync_preferences WHERE account_id = ?", (account_id,)).fetchone()
        return dict(row) if row else None

    def onboarding_status(self) -> dict[str, Any]:
        accounts = self.list_accounts()
        preferences = {item["id"]: self.get_sync_preferences(item["id"]) for item in accounts}
        jobs = {item["id"]: self.get_sync_job(item["id"]) for item in accounts}
        imported = bool(accounts) and all(preferences.values()) and all(item["last_synced_at"] for item in accounts)
        return {"profile": self.get_profile(), "profile_complete": self.profile_complete(), "accounts": accounts, "sync_preferences": preferences,
                "sync_jobs": jobs, "ready": self.profile_complete() and imported}

    def upsert_mail_source(self, account_id: str, provider: str, message_id: str, title: str, snippet: str, sent_at: str, sender: str, folder: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO mail_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, message_id) DO UPDATE SET title=excluded.title, snippet=excluded.snippet,
                sent_at=excluded.sent_at, sender=excluded.sender, folder=excluded.folder""",
                (provider, account_id, message_id, title, snippet, sent_at, sender, folder))

    def search_mail_sources(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        words = [word for word in re.findall(r"[a-z0-9]{3,}", query.lower()) if word not in {"what", "when", "show", "about", "needs", "attention", "with", "this", "week", "today", "email", "inbox", "please", "find", "from", "waiting", "follow", "reply", "recent", "important"}]
        with self.connect() as connection:
            rows = connection.execute("""SELECT m.*, a.display_name, a.email FROM mail_sources m JOIN connected_accounts a ON a.id=m.account_id ORDER BY sent_at DESC LIMIT 300""").fetchall()
        scored = [(sum(word in (row["title"] + " " + row["snippet"] + " " + row["sender"]).lower() for word in words), dict(row)) for row in rows]
        return [row for score, row in sorted(scored, key=lambda item: (item[0], item[1]["sent_at"]), reverse=True) if score or not words][:limit]

    def start_sync_job(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO sync_jobs VALUES (?, 'running', 0, NULL, ?, ?, NULL)
                ON CONFLICT(account_id) DO UPDATE SET status='running', error=NULL, updated_at=excluded.updated_at,
                processed_count=CASE WHEN sync_jobs.status='complete' THEN 0 ELSE sync_jobs.processed_count END""",
                (account_id, now_iso(), now_iso()))

    def reset_sync_job(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            related = {row["id"] for row in connection.execute("SELECT id, sources FROM actions")
                if any(source.get("source_id", "").startswith(f"{account_id}:") for source in json.loads(row["sources"]))}
            for action_id in related:
                connection.execute("DELETE FROM actions WHERE id=?", (action_id,))
            self._remove_action_cards(connection, related)
            connection.execute("DELETE FROM mail_sources WHERE account_id=?", (account_id,))
            connection.execute("DELETE FROM sync_jobs WHERE account_id=?", (account_id,))
            connection.execute("UPDATE connected_accounts SET last_synced_at=NULL, sync_error=NULL WHERE id=?", (account_id,))

    def update_sync_job(self, account_id: str, status: str, page_token: str | None = None, increment: int = 0, error: str | None = None) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("""UPDATE sync_jobs SET status=?, page_token=?, processed_count=processed_count+?, updated_at=?, error=? WHERE account_id=?""",
                (status, page_token, increment, now_iso(), error, account_id))
            if status == "complete":
                connection.execute("UPDATE connected_accounts SET last_synced_at=?, sync_error=NULL WHERE id=?", (now_iso(), account_id))
            elif status == "failed":
                connection.execute("UPDATE connected_accounts SET sync_error=? WHERE id=?", (error, account_id))

    def get_sync_job(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sync_jobs WHERE account_id=?", (account_id,)).fetchone()
        return dict(row) if row else None
