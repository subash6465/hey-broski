from __future__ import annotations

import json
import hashlib
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
        CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(content, content='document_chunks', content_rowid='rowid');
        CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
            INSERT INTO document_chunks_fts(rowid, content) VALUES (new.rowid, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
            INSERT INTO document_chunks_fts(document_chunks_fts, rowid, content) VALUES ('delete', old.rowid, old.content);
        END;
        CREATE TABLE IF NOT EXISTS reminders (id TEXT PRIMARY KEY, action_id TEXT NOT NULL UNIQUE REFERENCES actions(id) ON DELETE CASCADE, title TEXT NOT NULL, due_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_log (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, entity_id TEXT, details TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS owner_profile (id INTEGER PRIMARY KEY CHECK (id = 1), first_name TEXT NOT NULL, last_name TEXT NOT NULL, age INTEGER NOT NULL, phone_number TEXT NOT NULL, gender TEXT NOT NULL, time_zone TEXT NOT NULL, updated_at TEXT NOT NULL, date_of_birth TEXT, country_code TEXT);
        CREATE TABLE IF NOT EXISTS connected_accounts (id TEXT PRIMARY KEY, provider TEXT NOT NULL, email TEXT NOT NULL, display_name TEXT NOT NULL, status TEXT NOT NULL, connected_at TEXT NOT NULL, last_synced_at TEXT, sync_error TEXT, UNIQUE(provider, email));
        CREATE TABLE IF NOT EXISTS oauth_attempts (state TEXT PRIMARY KEY, provider TEXT NOT NULL, code_verifier TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_preferences (account_id TEXT PRIMARY KEY REFERENCES connected_accounts(id) ON DELETE CASCADE, history_months INTEGER NOT NULL, interval_hours INTEGER NOT NULL, include_sent INTEGER NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS mail_sources (provider TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES connected_accounts(id) ON DELETE CASCADE, message_id TEXT NOT NULL, title TEXT NOT NULL, snippet TEXT NOT NULL, sent_at TEXT NOT NULL, sender TEXT NOT NULL, folder TEXT NOT NULL, PRIMARY KEY(account_id, message_id));
        CREATE TABLE IF NOT EXISTS mail_messages (
            account_id TEXT NOT NULL REFERENCES connected_accounts(id) ON DELETE CASCADE,
            message_id TEXT NOT NULL, provider TEXT NOT NULL, thread_id TEXT NOT NULL,
            rfc_message_id TEXT, subject TEXT NOT NULL, sender_name TEXT NOT NULL,
            sender_address TEXT NOT NULL, to_json TEXT NOT NULL, cc_json TEXT NOT NULL,
            bcc_json TEXT NOT NULL, direction TEXT NOT NULL, received_at TEXT NOT NULL,
            header_date TEXT, labels_json TEXT NOT NULL, body_text TEXT NOT NULL,
            attachments_json TEXT NOT NULL, has_attachments INTEGER NOT NULL, seen_sync_at TEXT,
            PRIMARY KEY(account_id, message_id));
        CREATE INDEX IF NOT EXISTS idx_mail_messages_latest ON mail_messages(account_id, direction, received_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mail_messages_thread ON mail_messages(account_id, thread_id);
        CREATE INDEX IF NOT EXISTS idx_mail_messages_sender ON mail_messages(account_id, sender_address, received_at DESC);
        CREATE TABLE IF NOT EXISTS mail_chunks (
            id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, message_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
            content TEXT NOT NULL, UNIQUE(account_id, message_id, chunk_index),
            FOREIGN KEY(account_id, message_id) REFERENCES mail_messages(account_id, message_id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_mail_chunks_pipeline ON mail_chunks(account_id, message_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS mail_chunks_fts USING fts5(subject, sender, content, content='mail_chunks', content_rowid='id');
        CREATE TRIGGER IF NOT EXISTS mail_chunks_ai AFTER INSERT ON mail_chunks BEGIN
            INSERT INTO mail_chunks_fts(rowid, subject, sender, content) VALUES (new.id, new.subject, new.sender, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS mail_chunks_ad AFTER DELETE ON mail_chunks BEGIN
            INSERT INTO mail_chunks_fts(mail_chunks_fts, rowid, subject, sender, content) VALUES ('delete', old.id, old.subject, old.sender, old.content);
        END;
        CREATE TABLE IF NOT EXISTS sync_jobs (account_id TEXT PRIMARY KEY REFERENCES connected_accounts(id) ON DELETE CASCADE, status TEXT NOT NULL, processed_count INTEGER NOT NULL DEFAULT 0, page_token TEXT, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT, total_estimate INTEGER, skipped_count INTEGER NOT NULL DEFAULT 0, cutoff_at TEXT);
        CREATE TABLE IF NOT EXISTS sync_manifest (account_id TEXT NOT NULL REFERENCES connected_accounts(id) ON DELETE CASCADE, message_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', PRIMARY KEY(account_id, message_id));
        CREATE TABLE IF NOT EXISTS mail_action_jobs (account_id TEXT NOT NULL REFERENCES connected_accounts(id) ON DELETE CASCADE, message_id TEXT NOT NULL, fingerprint TEXT NOT NULL, processed_fingerprint TEXT, error TEXT, PRIMARY KEY(account_id, message_id));
        CREATE INDEX IF NOT EXISTS idx_mail_action_jobs ON mail_action_jobs(account_id, processed_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_sync_manifest_pending ON sync_manifest(account_id, state);
        CREATE INDEX IF NOT EXISTS idx_mail_sources_account_date ON mail_sources(account_id, sent_at);
        """
        with self._lock, self.connect() as connection:
            had_document_fts = connection.execute("SELECT 1 FROM sqlite_master WHERE name='document_chunks_fts'").fetchone() is not None
            connection.executescript(schema)
            profile_columns = {row[1] for row in connection.execute("PRAGMA table_info(owner_profile)")}
            for name in ("date_of_birth", "country_code"):
                if name not in profile_columns:
                    connection.execute(f"ALTER TABLE owner_profile ADD COLUMN {name} TEXT")
            job_columns = {row[1] for row in connection.execute("PRAGMA table_info(sync_jobs)")}
            for name, declaration in (("total_estimate", "INTEGER"), ("skipped_count", "INTEGER NOT NULL DEFAULT 0"), ("cutoff_at", "TEXT"), ("initial_history_id", "TEXT"), ("discovery_complete", "INTEGER NOT NULL DEFAULT 0")):
                if name not in job_columns:
                    connection.execute(f"ALTER TABLE sync_jobs ADD COLUMN {name} {declaration}")
            account_columns = {row[1] for row in connection.execute("PRAGMA table_info(connected_accounts)")}
            if "gmail_history_id" not in account_columns:
                connection.execute("ALTER TABLE connected_accounts ADD COLUMN gmail_history_id TEXT")
            if "mail_index_backfill_at" not in account_columns:
                connection.execute("ALTER TABLE connected_accounts ADD COLUMN mail_index_backfill_at TEXT")
            chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(mail_chunks)")}
            if "vector_model" not in chunk_columns:
                connection.execute("ALTER TABLE mail_chunks ADD COLUMN vector_model TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_mail_chunks_account_model ON mail_chunks(account_id, vector_model, message_id)")
            mail_columns = {row[1] for row in connection.execute("PRAGMA table_info(mail_messages)")}
            if "seen_sync_at" not in mail_columns:
                connection.execute("ALTER TABLE mail_messages ADD COLUMN seen_sync_at TEXT")
            for row in connection.execute("""SELECT s.account_id,s.message_id,s.title,COALESCE(m.body_text,s.snippet) AS body
                FROM mail_sources s LEFT JOIN mail_messages m ON m.account_id=s.account_id AND m.message_id=s.message_id
                WHERE NOT EXISTS (SELECT 1 FROM mail_action_jobs j WHERE j.account_id=s.account_id AND j.message_id=s.message_id)"""):
                fingerprint = hashlib.sha256(f"{row['title']}\n{row['body']}".encode()).hexdigest()
                connection.execute("INSERT INTO mail_action_jobs(account_id,message_id,fingerprint) VALUES (?,?,?)",
                                   (row["account_id"], row["message_id"], fingerprint))
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
            if not had_document_fts:
                connection.execute("INSERT INTO document_chunks_fts(document_chunks_fts) VALUES ('rebuild')")
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

    def edit_action(self, action_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"title", "description", "priority", "due_at", "status"}
        changes = {key: value for key, value in changes.items() if key in allowed}
        if not changes:
            return self.get_action(action_id)
        with self._lock, self.connect() as connection:
            connection.execute(f"UPDATE actions SET {','.join(key + '=?' for key in changes)}, updated_at=? WHERE id=?",
                               (*changes.values(), now_iso(), action_id))
            if "title" in changes or "due_at" in changes:
                connection.execute("UPDATE reminders SET title=COALESCE(?,title), due_at=COALESCE(?,due_at) WHERE action_id=?",
                                   (changes.get("title"), changes.get("due_at"), action_id))
        return self.get_action(action_id)

    def delete_action(self, action_id: str) -> bool:
        with self._lock, self.connect() as connection:
            changed = connection.execute("DELETE FROM actions WHERE id=?", (action_id,)).rowcount > 0
            if changed:
                self._remove_action_cards(connection, {action_id})
        return changed

    def execute_local_reminder(self, action_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Create the local side effect and status update in one transaction."""
        reminder_id, timestamp = f"reminder_{uuid4().hex}", now_iso()
        with self._lock, self.connect() as connection:
            action = connection.execute("SELECT * FROM actions WHERE id = ? AND status = 'pending'", (action_id,)).fetchone()
            if not action:
                return self.get_action(action_id), {"executed": False}
            connection.execute(
                """INSERT INTO reminders VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(action_id) DO UPDATE SET title=excluded.title, due_at=excluded.due_at""",
                (reminder_id, action_id, action["title"], action["due_at"], timestamp),
            )
            reminder_id = connection.execute("SELECT id FROM reminders WHERE action_id=?", (action_id,)).fetchone()[0]
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
        if not terms:
            return []
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in sorted(terms)[:12])
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute("""SELECT c.document_id, c.chunk_index, c.content, d.filename, d.created_at
                FROM document_chunks_fts JOIN document_chunks c ON c.rowid=document_chunks_fts.rowid
                JOIN documents d ON d.id=c.document_id WHERE document_chunks_fts MATCH ?
                ORDER BY bm25(document_chunks_fts), d.created_at DESC LIMIT ?""", (match, limit * 4))]
            filename_rows = [dict(row) for row in connection.execute("""SELECT c.document_id, c.chunk_index, c.content, d.filename, d.created_at
                FROM documents d JOIN document_chunks c ON c.document_id=d.id AND c.chunk_index=0
                WHERE """ + " OR ".join("lower(d.filename) LIKE ?" for _ in terms) + " ORDER BY d.created_at DESC LIMIT ?",
                (*[f"%{term}%" for term in sorted(terms)], limit))]
            document_count = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
            fallback = [dict(row) for row in connection.execute("""SELECT c.document_id, c.chunk_index, c.content, d.filename, d.created_at
                FROM document_chunks c JOIN documents d ON d.id=c.document_id ORDER BY c.chunk_index LIMIT ?""", (limit,))] if document_count == 1 else []
        unique: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows + filename_rows:
            unique.setdefault((row["document_id"], row["chunk_index"]), row)
        return list(unique.values())[:limit] or fallback

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
        configured = bool(accounts) and all(preferences.values())
        return {"profile": self.get_profile(), "profile_complete": self.profile_complete(), "accounts": accounts, "sync_preferences": preferences,
                "sync_jobs": jobs, "ready": self.profile_complete() and configured}

    def upsert_mail_source(self, account_id: str, provider: str, message_id: str, title: str, snippet: str, sent_at: str, sender: str, folder: str, content_fingerprint: str | None = None) -> None:
        fingerprint = content_fingerprint or hashlib.sha256(f"{title}\n{snippet}".encode()).hexdigest()
        with self._lock, self.connect() as connection:
            connection.execute("""INSERT INTO mail_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id, message_id) DO UPDATE SET title=excluded.title, snippet=excluded.snippet,
                sent_at=excluded.sent_at, sender=excluded.sender, folder=excluded.folder""",
                (provider, account_id, message_id, title, snippet, sent_at, sender, folder))
            connection.execute("""INSERT INTO mail_action_jobs(account_id,message_id,fingerprint) VALUES (?,?,?)
                ON CONFLICT(account_id,message_id) DO UPDATE SET fingerprint=excluded.fingerprint,
                error=CASE WHEN mail_action_jobs.fingerprint=excluded.fingerprint THEN mail_action_jobs.error ELSE NULL END""",
                (account_id, message_id, fingerprint))

    def pending_mail_actions(self, limit: int = 5) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""SELECT j.*, s.provider, s.title, s.snippet, s.sent_at, s.sender,
                COALESCE(m.body_text, s.snippet) AS body_text, a.email AS account_email, a.status AS account_status
                FROM mail_action_jobs j JOIN mail_sources s ON s.account_id=j.account_id AND s.message_id=j.message_id
                JOIN connected_accounts a ON a.id=j.account_id
                JOIN sync_jobs sync ON sync.account_id=j.account_id AND sync.status='complete'
                LEFT JOIN mail_messages m ON m.account_id=j.account_id AND m.message_id=j.message_id
                WHERE (j.processed_fingerprint IS NULL OR j.processed_fingerprint!=j.fingerprint)
                ORDER BY (j.error IS NOT NULL), s.sent_at, j.message_id LIMIT ?""", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def mail_action_candidates(self, account_id: str, subject: str, limit: int = 20) -> list[dict[str, Any]]:
        # Keep the scope account-local. The model receives IDs only from this list.
        with self.connect() as connection:
            rows = connection.execute("""SELECT * FROM actions WHERE id LIKE 'action_mail_%'
                AND status IN ('pending','completed') AND EXISTS
                (SELECT 1 FROM json_each(actions.sources) WHERE json_extract(value,'$.source_id') LIKE ?)
                ORDER BY updated_at DESC""", (f"{account_id}:%",)).fetchall()
        owned = [self._decode_action(row) for row in rows if any(s.get("source_id", "").startswith(f"{account_id}:") for s in json.loads(row["sources"]))]
        terms = set(re.findall(r"[a-z0-9]{3,}", subject.lower())) - {"your", "re", "fw", "fwd", "the", "and"}
        owned.sort(key=lambda card: sum(term in f"{card['title']} {card['description']}".lower() for term in terms), reverse=True)
        return owned[:limit]

    def apply_mail_action_events(self, job: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        changed: list[str] = []
        with self._lock, self.connect() as connection:
            current = connection.execute("SELECT fingerprint, processed_fingerprint FROM mail_action_jobs WHERE account_id=? AND message_id=?", (job["account_id"], job["message_id"])).fetchone()
            if not current or current["fingerprint"] != job["fingerprint"] or current["processed_fingerprint"] == job["fingerprint"]:
                return []
            for event in events:
                if event["operation"] == "create":
                    card = event["card"]
                    inserted = connection.execute("""INSERT OR IGNORE INTO actions(id,session_id,card_type,title,description,priority,status,due_at,confidence,sources,proposed_action,created_at,updated_at)
                        VALUES (?,NULL,'mail_task',?,?,?,?,?,?,?,NULL,?,?)""",
                        (card["id"], card["title"], card["description"], card["priority"], card["status"], card["due_at"], card["confidence"], json.dumps(card["sources"]), now_iso(), now_iso()))
                    if inserted.rowcount:
                        changed.append(card["id"])
                else:
                    row = connection.execute("SELECT * FROM actions WHERE id=?", (event["target_id"],)).fetchone()
                    if not row or row["status"] == "dismissed":
                        continue
                    sources = json.loads(row["sources"])
                    source = event["source"]
                    if not any(item.get("source_id") == source["source_id"] for item in sources):
                        sources.append(source)
                    connection.execute("""UPDATE actions SET title=?,description=?,priority=?,status=?,due_at=?,confidence=?,sources=?,updated_at=? WHERE id=?""",
                        (event["title"], event["description"], event["priority"], event["status"], event["due_at"], event["confidence"], json.dumps(sources), now_iso(), event["target_id"]))
                    changed.append(event["target_id"])
            connection.execute("UPDATE mail_action_jobs SET processed_fingerprint=fingerprint,error=NULL WHERE account_id=? AND message_id=?", (job["account_id"], job["message_id"]))
        return [card for action_id in changed if (card := self.get_action(action_id))]

    def fail_mail_action(self, account_id: str, message_id: str, error: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE mail_action_jobs SET error=? WHERE account_id=? AND message_id=?", (error[:240], account_id, message_id))

    def upsert_mail_message(self, item: dict[str, Any], seen_sync_at: str | None = None) -> None:
        """Persist one normalized message and replace its search chunks atomically."""
        columns = ("account_id", "message_id", "provider", "thread_id", "rfc_message_id", "subject",
                   "sender_name", "sender_address", "to_json", "cc_json", "bcc_json", "direction",
                   "received_at", "header_date", "labels_json", "body_text", "attachments_json", "has_attachments")
        values = tuple(json.dumps(item[key]) if key.endswith("_json") else item[key] for key in columns)
        with self._lock, self.connect() as connection:
            connection.execute(f"INSERT INTO mail_messages ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) "
                               f"ON CONFLICT(account_id, message_id) DO UPDATE SET " +
                               ",".join(f"{key}=excluded.{key}" for key in columns[2:]), values)
            if seen_sync_at:
                connection.execute("UPDATE mail_messages SET seen_sync_at=? WHERE account_id=? AND message_id=?",
                                   (seen_sync_at, item["account_id"], item["message_id"]))
            connection.execute("DELETE FROM mail_chunks WHERE account_id=? AND message_id=?", (item["account_id"], item["message_id"]))
            for index, chunk in enumerate(document_chunks(item["body_text"], size=1400, overlap=160) or [item["subject"]]):
                connection.execute("INSERT INTO mail_chunks(account_id,message_id,chunk_index,subject,sender,content) VALUES (?,?,?,?,?,?)",
                                   (item["account_id"], item["message_id"], index, item["subject"],
                                    f"{item['sender_name']} {item['sender_address']}", chunk))

    def search_mail_messages(self, query: str, *, direction: str | None = None, sender: str | None = None,
                             recipient: str | None = None, attachment_name: str | None = None,
                             exact_attachment_name: bool = False, subject_exact: str | None = None,
                             account_email: str | None = None,
                             latest: bool = False, attachments_only: bool = False,
                             after_at: str | None = None, before_at: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        where = ["1=1"]
        params: list[Any] = []
        if direction:
            where.append("m.direction=?")
            params.append(direction)
        if sender:
            compact = re.sub(r"[^a-z0-9]", "", sender.lower())
            where.append("(lower(m.sender_name || m.sender_address) LIKE ? OR lower(replace(m.sender_name || m.sender_address,' ','')) LIKE ?)")
            params.extend([f"%{sender.lower()}%", f"%{compact}%"])
        if recipient:
            where.append("""(EXISTS (SELECT 1 FROM json_each(m.to_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.cc_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.bcc_json) WHERE lower(value) LIKE ?))""")
            params.extend([f"%{recipient.lower()}%"] * 3)
        if attachment_name:
            comparator = "=" if exact_attachment_name else "LIKE"
            where.append(f"EXISTS (SELECT 1 FROM json_each(m.attachments_json) WHERE lower(json_extract(value,'$.name')) {comparator} ?)")
            params.append(attachment_name.lower() if exact_attachment_name else f"%{attachment_name.lower()}%")
        if subject_exact:
            where.append("lower(m.subject)=?")
            params.append(subject_exact.lower())
        if account_email:
            where.append("a.email=?")
            params.append(account_email.lower())
        if attachments_only:
            where.append("m.has_attachments=1")
        if after_at:
            where.append("m.received_at>=?")
            params.append(after_at)
        if before_at:
            where.append("m.received_at<?")
            params.append(before_at)
        base = " FROM mail_messages m JOIN connected_accounts a ON a.id=m.account_id "
        terms = [word for word in re.findall(r"[\w@.]+", query.lower()) if len(word) > 1 and not word.isdigit() and word not in
                 {"what", "which", "where", "when", "please", "could", "would", "tell", "show", "about", "regarding",
                  "mail", "mails", "email", "emails", "received", "sent", "from", "details", "the", "with", "this",
                  "latest", "newest", "recent", "most", "last", "find", "get", "me", "is", "i", "my", "was", "has",
                  "that", "mentioning", "containing", "saying", "inbox", "message", "messages",
                  "today", "yesterday", "week", "month", "day", "days", "since", "between"}]
        if sender:
            sender_compact = re.sub(r"[^a-z0-9]", "", sender.lower())
            terms = [word for word in terms if re.sub(r"[^a-z0-9]", "", word) not in sender_compact]
        if latest and not terms:
            sql = "SELECT m.*, a.email AS account_email, a.last_synced_at, c.content AS match_content, " \
                  "(SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count" + base + \
                  "LEFT JOIN mail_chunks c ON c.account_id=m.account_id AND c.message_id=m.message_id AND c.chunk_index=0 WHERE " + " AND ".join(where) + \
                  " ORDER BY m.received_at DESC LIMIT ?"
            with self.connect() as connection:
                return [dict(row) for row in connection.execute(sql, (*params, limit))]
        if not terms:
            return self.search_mail_messages(query, direction=direction, sender=sender, latest=True,
                                             recipient=recipient, attachment_name=attachment_name, account_email=account_email,
                                             exact_attachment_name=exact_attachment_name, subject_exact=subject_exact,
                                             attachments_only=attachments_only, after_at=after_at,
                                             before_at=before_at, limit=limit)
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms[:12])
        if latest:
            sql = """WITH matched AS (
                SELECT DISTINCT c.account_id, c.message_id FROM mail_chunks_fts
                JOIN mail_chunks c ON c.id=mail_chunks_fts.rowid WHERE mail_chunks_fts MATCH ?)
                SELECT m.*, a.email AS account_email, a.last_synced_at, m.body_text AS match_content,
                (SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count
                FROM matched x JOIN mail_messages m ON m.account_id=x.account_id AND m.message_id=x.message_id
                JOIN connected_accounts a ON a.id=m.account_id WHERE """ + " AND ".join(where) + " ORDER BY m.received_at DESC LIMIT ?"
            with self.connect() as connection:
                return [dict(row) for row in connection.execute(sql, (match, *params, limit))]
        sql = "SELECT m.*, a.email AS account_email, a.last_synced_at, c.id AS chunk_id, c.content AS match_content, " \
              "(SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count, " \
              "bm25(mail_chunks_fts, 4.0, 3.0, 1.0) AS score" + base + \
              "JOIN mail_chunks c ON c.account_id=m.account_id AND c.message_id=m.message_id " \
              "JOIN mail_chunks_fts ON mail_chunks_fts.rowid=c.id WHERE mail_chunks_fts MATCH ? AND " + " AND ".join(where) + \
              " ORDER BY score, m.received_at DESC LIMIT ?"
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, (match, *params, max(100, limit * 20)))]
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            unique.setdefault((row["account_id"], row["message_id"]), row)
        return list(unique.values())[:limit]

    def indexed_mail_count(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT count(*) FROM mail_messages").fetchone()[0]

    def indexed_document_count(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT count(*) FROM documents").fetchone()[0]

    def has_summary_only_mail_accounts(self) -> bool:
        with self.connect() as connection:
            return bool(connection.execute("SELECT EXISTS(SELECT 1 FROM connected_accounts WHERE provider<>'gmail')").fetchone()[0])

    def count_mail_messages(self, *, direction: str | None = None, sender: str | None = None,
                            recipient: str | None = None, attachment_name: str | None = None,
                            attachments_only: bool = False, after_at: str | None = None,
                            before_at: str | None = None, account_email: str | None = None) -> int:
        clauses = ["1=1"]
        params: list[Any] = []
        if direction:
            clauses.append("m.direction=?")
            params.append(direction)
        if sender:
            compact = re.sub(r"[^a-z0-9]", "", sender.lower())
            clauses.append("(lower(m.sender_name || m.sender_address) LIKE ? OR lower(replace(m.sender_name || m.sender_address,' ','')) LIKE ?)")
            params.extend([f"%{sender.lower()}%", f"%{compact}%"])
        if recipient:
            clauses.append("""(EXISTS (SELECT 1 FROM json_each(m.to_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.cc_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.bcc_json) WHERE lower(value) LIKE ?))""")
            params.extend([f"%{recipient.lower()}%"] * 3)
        if attachment_name:
            clauses.append("EXISTS (SELECT 1 FROM json_each(m.attachments_json) WHERE lower(json_extract(value,'$.name')) LIKE ?)")
            params.append(f"%{attachment_name.lower()}%")
        if attachments_only:
            clauses.append("m.has_attachments=1")
        if after_at:
            clauses.append("m.received_at>=?")
            params.append(after_at)
        if before_at:
            clauses.append("m.received_at<?")
            params.append(before_at)
        if account_email:
            clauses.append("a.email=?")
            params.append(account_email.lower())
        with self.connect() as connection:
            return connection.execute("SELECT count(*) FROM mail_messages m JOIN connected_accounts a ON a.id=m.account_id WHERE " +
                                      " AND ".join(clauses), params).fetchone()[0]

    def mail_thread(self, account_id: str, thread_id: str, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT m.*, a.email AS account_email, a.last_synced_at,
                (SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count
                FROM mail_messages m JOIN connected_accounts a ON a.id=m.account_id
                WHERE m.account_id=? AND m.thread_id=? ORDER BY m.received_at LIMIT ? OFFSET ?""",
                (account_id, thread_id, limit, offset))]

    def mail_message(self, account_id: str, message_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("""SELECT m.*, a.email AS account_email, a.last_synced_at,
                (SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count
                FROM mail_messages m JOIN connected_accounts a ON a.id=m.account_id
                WHERE m.account_id=? AND m.message_id=?""", (account_id, message_id)).fetchone()
        return dict(row) if row else None

    def needs_gmail_backfill(self, account_id: str) -> bool:
        with self.connect() as connection:
            account = connection.execute("SELECT mail_index_backfill_at FROM connected_accounts WHERE id=?", (account_id,)).fetchone()
            if not account or account["mail_index_backfill_at"]:
                return False
            old_count = connection.execute("SELECT count(*) FROM mail_sources WHERE account_id=? AND provider='gmail'", (account_id,)).fetchone()[0]
            new_count = connection.execute("SELECT count(*) FROM mail_messages WHERE account_id=?", (account_id,)).fetchone()[0]
        return old_count > 0 and new_count == 0

    def mark_mail_index_backfilled(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE connected_accounts SET mail_index_backfill_at=? WHERE id=?", (now_iso(), account_id))

    def pending_mail_vectors(self, model: str, limit: int = 16) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("""SELECT c.id, c.account_id, c.message_id, c.subject, c.sender, c.content
                FROM mail_chunks c LEFT JOIN sync_jobs j ON j.account_id=c.account_id
                WHERE (c.vector_model IS NULL OR c.vector_model<>?)
                AND (j.status IS NULL OR j.status NOT IN ('paused','paused_processing','canceled'))
                ORDER BY c.id LIMIT ?""", (model, limit)).fetchall()
        return [dict(row) for row in rows]

    def pending_mail_vector_count(self, model: str) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT count(*) FROM mail_chunks WHERE vector_model IS NULL OR vector_model<>?", (model,)).fetchone()[0]

    def mail_pipeline_counts(self, account_id: str, model: str) -> dict[str, int]:
        with self.connect() as connection:
            searchable = connection.execute("SELECT count(*) FROM mail_messages WHERE account_id=?", (account_id,)).fetchone()[0]
            pending_chunks, pending_messages = connection.execute("""SELECT count(*), count(DISTINCT message_id)
                FROM mail_chunks WHERE account_id=? AND (vector_model IS NULL OR vector_model<>?)""",
                (account_id, model)).fetchone()
            imported, processed = connection.execute("""SELECT count(*), coalesce(sum(CASE WHEN NOT EXISTS
                (SELECT 1 FROM mail_chunks c WHERE c.account_id=m.account_id AND c.message_id=m.message_id
                    AND (c.vector_model IS NULL OR c.vector_model<>?)) THEN 1 ELSE 0 END), 0)
                FROM sync_manifest m WHERE m.account_id=? AND m.state='imported'""", (model, account_id)).fetchone()
            discovered = connection.execute("SELECT count(*) FROM sync_manifest WHERE account_id=?", (account_id,)).fetchone()[0]
            action_total, action_processed = connection.execute("""SELECT count(*),coalesce(sum(processed_fingerprint=fingerprint),0)
                FROM mail_action_jobs WHERE account_id=?""", (account_id,)).fetchone()
        return {"searchable_messages": searchable, "embedded_messages": searchable - pending_messages,
                "pending_embedding_chunks": pending_chunks, "imported_messages": imported,
                "processed_messages": processed, "discovered_messages": discovered,
                "action_messages_total": action_total, "action_messages_processed": action_processed}

    def initial_mail_import_incomplete(self) -> bool:
        with self.connect() as connection:
            return connection.execute("""SELECT EXISTS(
                SELECT 1 FROM connected_accounts a JOIN sync_preferences p ON p.account_id=a.id
                WHERE a.last_synced_at IS NULL OR
                    (a.provider='gmail' AND a.mail_index_backfill_at IS NULL AND EXISTS
                        (SELECT 1 FROM mail_sources s WHERE s.account_id=a.id)))""").fetchone()[0] == 1

    def inaccessible_mail_count(self) -> int:
        with self.connect() as connection:
            return connection.execute("SELECT coalesce(sum(skipped_count),0) FROM sync_jobs").fetchone()[0]

    def mark_mail_vectors(self, ids: list[int], model: str) -> None:
        if not ids:
            return
        with self._lock, self.connect() as connection:
            connection.execute(f"UPDATE mail_chunks SET vector_model=? WHERE id IN ({','.join('?' for _ in ids)})",
                               (model, *ids))

    def mail_messages_for_chunks(self, ids: list[int], *, direction: str | None = None,
                                 sender: str | None = None, recipient: str | None = None,
                                 attachment_name: str | None = None, account_email: str | None = None,
                                 attachments_only: bool = False,
                                 after_at: str | None = None, before_at: str | None = None) -> list[dict[str, Any]]:
        if not ids:
            return []
        where = [f"c.id IN ({','.join('?' for _ in ids)})"]
        params: list[Any] = list(ids)
        if direction:
            where.append("m.direction=?")
            params.append(direction)
        if sender:
            compact = re.sub(r"[^a-z0-9]", "", sender.lower())
            where.append("(lower(m.sender_name || m.sender_address) LIKE ? OR lower(replace(m.sender_name || m.sender_address,' ','')) LIKE ?)")
            params.extend([f"%{sender.lower()}%", f"%{compact}%"])
        if recipient:
            where.append("""(EXISTS (SELECT 1 FROM json_each(m.to_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.cc_json) WHERE lower(value) LIKE ?)
                OR EXISTS (SELECT 1 FROM json_each(m.bcc_json) WHERE lower(value) LIKE ?))""")
            params.extend([f"%{recipient.lower()}%"] * 3)
        if attachment_name:
            where.append("EXISTS (SELECT 1 FROM json_each(m.attachments_json) WHERE lower(json_extract(value,'$.name')) LIKE ?)")
            params.append(f"%{attachment_name.lower()}%")
        if account_email:
            where.append("a.email=?")
            params.append(account_email.lower())
        if attachments_only:
            where.append("m.has_attachments=1")
        if after_at:
            where.append("m.received_at>=?")
            params.append(after_at)
        if before_at:
            where.append("m.received_at<?")
            params.append(before_at)
        sql = "SELECT m.*, a.email AS account_email, a.last_synced_at, c.id AS chunk_id, c.content AS match_content, " \
              "(SELECT count(*) FROM mail_messages t WHERE t.account_id=m.account_id AND t.thread_id=m.thread_id) AS thread_count " \
              "FROM mail_chunks c JOIN mail_messages m ON m.account_id=c.account_id AND m.message_id=c.message_id " \
              "JOIN connected_accounts a ON a.id=m.account_id WHERE " + " AND ".join(where)
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, params)]
        by_id = {row_id: position for position, row_id in enumerate(ids)}
        rows.sort(key=lambda row: by_id.get(row["chunk_id"], len(ids)))
        return rows

    def set_gmail_history_id(self, account_id: str, history_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE connected_accounts SET gmail_history_id=? WHERE id=?", (history_id, account_id))

    def delete_mail_message(self, account_id: str, message_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM mail_action_jobs WHERE account_id=? AND message_id=?", (account_id, message_id))
            connection.execute("DELETE FROM mail_messages WHERE account_id=? AND message_id=?", (account_id, message_id))
            connection.execute("DELETE FROM mail_sources WHERE account_id=? AND message_id=?", (account_id, message_id))

    def reconcile_full_gmail_scan(self, account_id: str, marker: str, cutoff_at: str, include_sent: bool) -> int:
        clause = "account_id=? AND received_at>=? AND (seen_sync_at IS NULL OR seen_sync_at<>?)"
        params: list[Any] = [account_id, cutoff_at, marker]
        if not include_sent:
            clause += " AND direction='received'"
        with self._lock, self.connect() as connection:
            stale = [row[0] for row in connection.execute(f"SELECT message_id FROM mail_messages WHERE {clause}", params)]
            for message_id in stale:
                connection.execute("DELETE FROM mail_action_jobs WHERE account_id=? AND message_id=?", (account_id, message_id))
                connection.execute("DELETE FROM mail_messages WHERE account_id=? AND message_id=?", (account_id, message_id))
                connection.execute("DELETE FROM mail_sources WHERE account_id=? AND message_id=?", (account_id, message_id))
        return len(stale)

    def search_mail_sources(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        words = [word for word in re.findall(r"[a-z0-9]{3,}", query.lower()) if word not in {"what", "when", "show", "about", "needs", "attention", "with", "this", "week", "today", "email", "inbox", "please", "find", "from", "waiting", "follow", "reply", "recent", "important"}]
        with self.connect() as connection:
            rows = connection.execute("""SELECT m.*, a.display_name, a.email FROM mail_sources m JOIN connected_accounts a ON a.id=m.account_id ORDER BY sent_at DESC LIMIT 300""").fetchall()
        scored = [(sum(word in (row["title"] + " " + row["snippet"] + " " + row["sender"]).lower() for word in words), dict(row)) for row in rows]
        return [row for score, row in sorted(scored, key=lambda item: (item[0], item[1]["sent_at"]), reverse=True) if score or not words][:limit]

    def start_sync_job(self, account_id: str, cutoff_at: str | None = None) -> None:
        with self._lock, self.connect() as connection:
            previous = connection.execute("SELECT status FROM sync_jobs WHERE account_id=?", (account_id,)).fetchone()
            if previous and previous[0] in {"complete", "canceled"}:
                connection.execute("DELETE FROM sync_manifest WHERE account_id=?", (account_id,))
            connection.execute("""INSERT INTO sync_jobs (account_id, status, processed_count, page_token, started_at, updated_at, error, cutoff_at)
                VALUES (?, 'running', 0, NULL, ?, ?, NULL, ?)
                ON CONFLICT(account_id) DO UPDATE SET status='running', error=NULL, updated_at=excluded.updated_at,
                started_at=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN excluded.started_at ELSE sync_jobs.started_at END,
                cutoff_at=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN excluded.cutoff_at ELSE COALESCE(sync_jobs.cutoff_at, excluded.cutoff_at) END,
                processed_count=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN 0 ELSE sync_jobs.processed_count END,
                skipped_count=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN 0 ELSE sync_jobs.skipped_count END,
                initial_history_id=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN NULL ELSE sync_jobs.initial_history_id END,
                total_estimate=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN NULL ELSE sync_jobs.total_estimate END,
                discovery_complete=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN 0 ELSE sync_jobs.discovery_complete END,
                page_token=CASE WHEN sync_jobs.status IN ('complete','canceled') THEN NULL ELSE sync_jobs.page_token END""",
                (account_id, now_iso(), now_iso(), cutoff_at))

    def set_sync_initial_history_id(self, account_id: str, history_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE sync_jobs SET initial_history_id=? WHERE account_id=?", (history_id, account_id))

    def restart_legacy_sync_discovery(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM sync_manifest WHERE account_id=?", (account_id,))
            connection.execute("""UPDATE sync_jobs SET page_token=NULL, processed_count=0, skipped_count=0,
                total_estimate=NULL, discovery_complete=0, initial_history_id=NULL, started_at=?, updated_at=?
                WHERE account_id=?""", (now_iso(), now_iso(), account_id))

    def set_sync_cutoff(self, account_id: str, cutoff_at: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE sync_jobs SET cutoff_at=?, initial_history_id=NULL WHERE account_id=?",
                               (cutoff_at, account_id))

    def reset_sync_job(self, account_id: str, purge_mail_conversations: bool = False) -> None:
        with self._lock, self.connect() as connection:
            if purge_mail_conversations:
                turns = {row["turn_id"] for row in connection.execute("SELECT turn_id, metadata FROM messages WHERE role='assistant'")
                    if any(source.get("source_id", "").startswith(f"{account_id}:")
                           for source in json.loads(row["metadata"]).get("sources", []))}
                for turn_id in turns:
                    connection.execute("DELETE FROM messages WHERE turn_id=?", (turn_id,))
            related = {row["id"] for row in connection.execute("SELECT id, sources FROM actions")
                if any(source.get("source_id", "").startswith(f"{account_id}:") for source in json.loads(row["sources"]))}
            for action_id in related:
                connection.execute("DELETE FROM actions WHERE id=?", (action_id,))
            self._remove_action_cards(connection, related)
            connection.execute("DELETE FROM mail_action_jobs WHERE account_id=?", (account_id,))
            connection.execute("DELETE FROM mail_sources WHERE account_id=?", (account_id,))
            connection.execute("DELETE FROM mail_messages WHERE account_id=?", (account_id,))
            connection.execute("DELETE FROM sync_jobs WHERE account_id=?", (account_id,))
            connection.execute("DELETE FROM sync_manifest WHERE account_id=?", (account_id,))
            connection.execute("UPDATE connected_accounts SET last_synced_at=NULL, sync_error=NULL WHERE id=?", (account_id,))
            connection.execute("UPDATE connected_accounts SET gmail_history_id=NULL WHERE id=?", (account_id,))
            connection.execute("UPDATE connected_accounts SET mail_index_backfill_at=NULL WHERE id=?", (account_id,))

    def update_sync_job(self, account_id: str, status: str, page_token: str | None = None, increment: int = 0, error: str | None = None, skipped: int = 0, total_estimate: int | None = None) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("""UPDATE sync_jobs SET status=?, page_token=?, processed_count=processed_count+?,
                skipped_count=skipped_count+?, total_estimate=COALESCE(?, total_estimate), updated_at=?, error=? WHERE account_id=?""",
                (status, page_token, increment, skipped, total_estimate, now_iso(), error, account_id))
            if status == "complete":
                connection.execute("UPDATE connected_accounts SET last_synced_at=?, sync_error=NULL WHERE id=?", (now_iso(), account_id))
            elif status == "failed":
                connection.execute("UPDATE connected_accounts SET sync_error=? WHERE id=?", (error, account_id))

    def get_sync_job(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sync_jobs WHERE account_id=?", (account_id,)).fetchone()
        return dict(row) if row else None

    def add_sync_page(self, account_id: str, message_ids: list[str], next_token: str | None) -> None:
        with self._lock, self.connect() as connection:
            connection.executemany("INSERT OR IGNORE INTO sync_manifest(account_id,message_id) VALUES (?,?)",
                                   [(account_id, message_id) for message_id in message_ids])
            discovered = connection.execute("SELECT count(*) FROM sync_manifest WHERE account_id=?", (account_id,)).fetchone()[0]
            connection.execute("""UPDATE sync_jobs SET page_token=?, total_estimate=?, discovery_complete=?, updated_at=?
                WHERE account_id=?""", (next_token, discovered, int(next_token is None), now_iso(), account_id))

    def pending_sync_messages(self, account_id: str, limit: int = 8) -> list[str]:
        with self.connect() as connection:
            return [row[0] for row in connection.execute("""SELECT message_id FROM sync_manifest
                WHERE account_id=? AND state='pending' ORDER BY rowid LIMIT ?""", (account_id, limit))]

    def finish_sync_message(self, account_id: str, message_id: str, skipped: bool = False) -> None:
        with self._lock, self.connect() as connection:
            changed = connection.execute("""UPDATE sync_manifest SET state=? WHERE account_id=? AND message_id=? AND state='pending'""",
                ('skipped' if skipped else 'imported', account_id, message_id)).rowcount
            if changed:
                connection.execute("""UPDATE sync_jobs SET processed_count=processed_count+?, skipped_count=skipped_count+?, updated_at=?
                    WHERE account_id=?""", (0 if skipped else 1, 1 if skipped else 0, now_iso(), account_id))

    def record_history_message(self, account_id: str, message_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("INSERT OR IGNORE INTO sync_manifest(account_id,message_id) VALUES (?,?)", (account_id, message_id))
        self.finish_sync_message(account_id, message_id)

    def drop_sync_message(self, account_id: str, message_id: str) -> None:
        with self._lock, self.connect() as connection:
            row = connection.execute("SELECT state FROM sync_manifest WHERE account_id=? AND message_id=?",
                                     (account_id, message_id)).fetchone()
            if row:
                connection.execute("DELETE FROM sync_manifest WHERE account_id=? AND message_id=?", (account_id, message_id))
                connection.execute("""UPDATE sync_jobs SET processed_count=max(0, processed_count-?),
                    skipped_count=max(0, skipped_count-?) WHERE account_id=?""",
                    (int(row["state"] == "imported"), int(row["state"] == "skipped"), account_id))

    def complete_history_discovery(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            count = connection.execute("SELECT count(*) FROM sync_manifest WHERE account_id=?", (account_id,)).fetchone()[0]
            connection.execute("UPDATE sync_jobs SET total_estimate=?, discovery_complete=1 WHERE account_id=?", (count, account_id))

    def clear_sync_manifest(self, account_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM sync_manifest WHERE account_id=?", (account_id,))
            connection.execute("UPDATE sync_jobs SET page_token=NULL, total_estimate=NULL, discovery_complete=0 WHERE account_id=?", (account_id,))

    def set_sync_control(self, account_id: str, status: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute("UPDATE sync_jobs SET status=?, updated_at=? WHERE account_id=?", (status, now_iso(), account_id))
