"""Bounded, read-only tools exposed to the local chat model."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx

from .repository import Repository
from .schemas import Source
from .mail_vectors import MailVectorIndex


TOOLS = [
    {"type": "function", "function": {"name": "search_mail", "description": "Search indexed mail using text and optional metadata filters. Use for facts in mail; call again with a different query if no result fits.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Distinctive words from the subject or body; empty for metadata-only search"},
            "sender": {"type": "string", "description": "Sender name or email only when specified by the user"},
            "recipient": {"type": "string", "description": "Recipient email, including To/Cc/Bcc, only when specified"},
            "attachment_name": {"type": "string", "description": "Partial attachment filename"},
            "account_email": {"type": "string", "description": "Connected account email when the user specified one"},
            "direction": {"type": "string", "enum": ["received", "sent"]},
            "attachments_only": {"type": "boolean"},
            "latest": {"type": "boolean", "description": "Use for newest mail without a topical text query"},
            "after_at": {"type": "string", "description": "Inclusive ISO 8601 UTC timestamp, only if the user specified a date range"},
            "before_at": {"type": "string", "description": "Exclusive ISO 8601 UTC timestamp, only if the user specified a date range"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "count_mail", "description": "Get an exact count of indexed messages matching metadata filters. Do not use for a topic or semantic concept.",
        "parameters": {"type": "object", "properties": {
            "sender": {"type": "string"}, "recipient": {"type": "string"}, "attachment_name": {"type": "string"},
            "direction": {"type": "string", "enum": ["received", "sent"]},
            "attachments_only": {"type": "boolean"}, "account_email": {"type": "string"},
            "after_at": {"type": "string"}, "before_at": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "open_message", "description": "Read the stored body and metadata of one cited mail message. Use when a snippet does not contain the requested detail.",
        "parameters": {"type": "object", "properties": {"source_number": {"type": "integer", "description": "1-based [Source N] number"}}, "required": ["source_number"]}}},
    {"type": "function", "function": {"name": "find_in_message", "description": "Find text inside a long cited mail message and return nearby exact passages, including text beyond the open_message limit.",
        "parameters": {"type": "object", "properties": {"source_number": {"type": "integer"}, "query": {"type": "string"}},
            "required": ["source_number", "query"]}}},
    {"type": "function", "function": {"name": "open_thread", "description": "Read other indexed messages in the thread of a cited mail message.",
        "parameters": {"type": "object", "properties": {"source_number": {"type": "integer", "description": "1-based [Source N] number"},
            "offset": {"type": "integer", "description": "Skip this many oldest messages when paging a long thread"}}, "required": ["source_number"]}}},
    {"type": "function", "function": {"name": "search_documents", "description": "Search uploaded local documents for relevant passages.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]


class AgentTools:
    def __init__(self, repository: Repository, sources: list[Source], vectors: MailVectorIndex | None = None,
                 question: str = "") -> None:
        self.repository = repository
        self.sources = sources
        self.vectors = vectors
        self.question = question.lower()

    def _add(self, source: Source) -> int:
        for index, existing in enumerate(self.sources, 1):
            if existing.source_type == source.source_type and existing.source_id == source.source_id:
                return index
        if len(self.sources) >= 30:
            raise ValueError("The source limit has been reached")
        self.sources.append(source)
        return len(self.sources)

    def _mail_source(self, row: dict[str, Any]) -> Source:
        return Source(source_type="email", source_id=f"{row['account_id']}:{row['message_id']}",
            account_label=f"{row['provider'].title()} / {row['account_email']}", title=row["subject"],
            snippet=(f"From: {row['sender_name']} <{row['sender_address']}>. "
                     f"To: {', '.join(json.loads(row['to_json']))}. Direction: {row['direction']}. "
                     f"Thread messages indexed: {row['thread_count']}. "
                     f"Attachments: {', '.join(item['name'] for item in json.loads(row['attachments_json'])) or 'none'}. "
                     f"Content: {(row.get('match_content') or row['body_text'])[:1800]}"),
            timestamp=row["received_at"], metadata={"account_id": row["account_id"],
                "message_id": row["message_id"], "thread_id": row["thread_id"],
                "sender": row["sender_address"], "direction": row["direction"],
                "thread_count_indexed": row["thread_count"], "last_synced_at": row["last_synced_at"],
                "attachments": json.loads(row["attachments_json"])})

    @staticmethod
    def _date(value: Any) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError("Invalid date filter")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Date filter needs a timezone")
        return parsed.isoformat()

    def _mail_filters(self, args: dict[str, Any]) -> dict[str, Any]:
        direction = args.get("direction")
        if direction not in (None, "received", "sent"):
            raise ValueError("Invalid mail direction")
        sender = args.get("sender")
        if sender is not None and (not isinstance(sender, str) or len(sender) > 150):
            raise ValueError("Invalid sender")
        recipient = args.get("recipient")
        attachment_name = args.get("attachment_name")
        account_email = args.get("account_email")
        if recipient is not None and (not isinstance(recipient, str) or len(recipient) > 150):
            raise ValueError("Invalid recipient")
        if attachment_name is not None and (not isinstance(attachment_name, str) or len(attachment_name) > 200):
            raise ValueError("Invalid attachment filename")
        if account_email is not None and (not isinstance(account_email, str) or len(account_email) > 254):
            raise ValueError("Invalid account email")
        return {"direction": direction, "sender": sender or None, "recipient": recipient or None,
                "attachment_name": attachment_name or None, "account_email": account_email or None,
                "attachments_only": args.get("attachments_only") is True,
                "after_at": self._date(args.get("after_at")), "before_at": self._date(args.get("before_at"))}

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        if name == "search_mail":
            query = args.get("query", "")
            if not isinstance(query, str) or len(query) > 300:
                raise ValueError("Invalid mail query")
            filters = self._mail_filters(args)
            latest = args.get("latest") is True
            rows = self.repository.search_mail_messages(query, latest=latest, limit=8, **filters)
            if query.strip() and self.vectors:
                try:
                    ids = self.vectors.search(query, limit=20)
                    semantic = self.repository.mail_messages_for_chunks(ids, **filters)
                    ranked: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
                    for weight, candidates in ((1.0, rows), (0.8, semantic)):
                        for rank, row in enumerate(candidates, 1):
                            key = (row["account_id"], row["message_id"])
                            score, previous = ranked.get(key, (0.0, row))
                            ranked[key] = (score + weight / (60 + rank), previous)
                    rows = [item for _, item in sorted(ranked.values(), key=lambda pair: pair[0], reverse=True)[:8]]
                except (ImportError, OSError, ValueError, RuntimeError, httpx.HTTPError):
                    pass
            found = [{"source": self._add(self._mail_source(row)), "subject": row["subject"],
                      "received_at": row["received_at"], "sender": row["sender_address"],
                      "excerpt": (row.get("match_content") or row["body_text"])[:1000]} for row in rows]
            return {"matches": found, "count_returned": len(found), "search_scope": "indexed mail"}
        if name == "count_mail":
            if re.search(r"\b(about|regarding|mentioning|containing)\b", self.question):
                raise ValueError("A topic cannot be counted with metadata-only count_mail; search first and describe the limit")
            filters = self._mail_filters(args)
            if filters["sender"] and re.sub(r"[^a-z0-9]", "", filters["sender"].lower()) not in re.sub(r"[^a-z0-9]", "", self.question):
                raise ValueError("Sender filter was not requested by the user")
            if filters["direction"] == "received" and not re.search(r"\b(receive|received|inbox|came in)\b", self.question):
                raise ValueError("Received-mail filter was not requested")
            if filters["direction"] == "sent" and not re.search(r"\b(sent|outgoing)\b", self.question):
                raise ValueError("Sent-mail filter was not requested")
            if filters["attachments_only"] and not re.search(r"\b(attachment|attachments|attached)\b", self.question):
                raise ValueError("Attachment filter was not requested")
            if filters["recipient"] and re.sub(r"[^a-z0-9]", "", filters["recipient"].lower()) not in re.sub(r"[^a-z0-9]", "", self.question):
                raise ValueError("Recipient filter was not requested")
            if filters["attachment_name"] and filters["attachment_name"].lower() not in self.question:
                raise ValueError("Attachment filename was not requested")
            if filters["account_email"] and filters["account_email"].lower() not in self.question:
                raise ValueError("Account filter was not requested by the user")
            return {"count": self.repository.count_mail_messages(**filters),
                    "scope": "fully indexed Gmail messages", "outlook_summary_only": self.repository.has_summary_only_mail_accounts(),
                    "initial_import_incomplete": self.repository.initial_mail_import_incomplete(),
                    "inaccessible_last_sync": self.repository.inaccessible_mail_count()}
        if name in {"open_message", "open_thread", "find_in_message"}:
            number = args.get("source_number")
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(self.sources):
                raise ValueError("Invalid source number")
            source = self.sources[number - 1]
            if source.source_type != "email":
                raise ValueError("Source is not mail")
            account_id, message_id = source.source_id.split(":", 1)
            row = self.repository.mail_message(account_id, message_id)
            if not row:
                return {"error": "Message is no longer indexed"}
            if name == "find_in_message":
                query = args.get("query")
                if not isinstance(query, str) or not query.strip() or len(query) > 150:
                    raise ValueError("Invalid passage query")
                body = row["body_text"]
                found = list(re.finditer(re.escape(query.strip()), body, re.IGNORECASE))[:3]
                if not found:
                    terms = [word for word in re.findall(r"[\w-]{3,}", query) if word.lower() not in {"what", "where", "when", "find", "about"}]
                    found = [match for term in terms[:3] for match in list(re.finditer(re.escape(term), body, re.IGNORECASE))[:1]][:3]
                return {"source": number, "passages": [body[max(0, match.start() - 400):match.end() + 400] for match in found],
                        "found": bool(found)}
            offset = args.get("offset", 0)
            if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 10000:
                raise ValueError("Invalid thread offset")
            rows = [row] if name == "open_message" else self.repository.mail_thread(account_id, row["thread_id"], limit=10, offset=offset)
            items = []
            for item in rows:
                index = self._add(self._mail_source(item))
                items.append({"source": index, "subject": item["subject"], "sender": item["sender_address"],
                    "received_at": item["received_at"], "body": item["body_text"][:8000 if name == "open_message" else 1200],
                    "body_truncated": len(item["body_text"]) > (8000 if name == "open_message" else 1200),
                    "attachments": json.loads(item["attachments_json"])})
            return {"messages": items, "thread_count_indexed": row["thread_count"],
                    "next_offset": offset + len(rows) if name == "open_thread" and row["thread_count"] > offset + len(rows) else None}
        if name == "search_documents":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip() or len(query) > 300:
                raise ValueError("Invalid document query")
            rows = self.repository.search_document_chunks(query)
            found = []
            for row in rows[:8]:
                source = Source(source_type="document", source_id=f'{row["document_id"]}#part-{row["chunk_index"] + 1}',
                    account_label="Document vault", title=f'{row["filename"]} (part {row["chunk_index"] + 1})',
                    snippet=row["content"], timestamp=row["created_at"])
                found.append({"source": self._add(source), "title": source.title, "excerpt": source.snippet[:1200]})
            return {"matches": found, "count_returned": len(found)}
        raise ValueError("Unknown tool")
