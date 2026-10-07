"""Normalize Gmail MIME messages without asking an LLM to interpret provider fields."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip += 1
        elif tag in {"p", "br", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError):
        return value


def _part_text(part: dict) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (ValueError, TypeError):
        return ""
    charset = "utf-8"
    for header in part.get("headers", []):
        if header.get("name", "").lower() == "content-type":
            found = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", header.get("value", ""), re.I)
            if found:
                charset = found.group(1)
            break
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def normalize_gmail_message(message: dict, account_id: str, account_email: str) -> dict:
    payload = message.get("payload") or {}
    headers = {entry.get("name", "").lower(): _decode(entry.get("value", "")) for entry in payload.get("headers", [])}
    sender = getaddresses([headers.get("from", "")])
    sender_name, sender_address = sender[0] if sender else ("", "")
    sender_address = sender_address.lower()
    labels = message.get("labelIds") or []
    direction = "sent" if "SENT" in labels or sender_address == account_email.lower() else "received"
    plain: list[str] = []
    html: list[str] = []
    attachments: list[dict] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        stack.extend(reversed(part.get("parts") or []))
        filename = _decode(part.get("filename") or "")
        if filename:
            body = part.get("body") or {}
            attachments.append({"name": filename, "mime_type": part.get("mimeType", ""),
                                "size": body.get("size", 0), "attachment_id": body.get("attachmentId")})
            continue
        mime = (part.get("mimeType") or "").lower()
        if mime == "text/plain":
            plain.append(_part_text(part))
        elif mime == "text/html":
            parser = _HTMLText()
            parser.feed(_part_text(part))
            html.append("".join(parser.parts))
    plain = [part for part in plain if part.strip() and not re.fullmatch(r"\s*please\s+enable\s+html[.!\s]*", part, re.I)]
    body = "\n".join(plain or [part for part in html if part.strip()]).strip() or message.get("snippet", "")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    header_date = None
    if headers.get("date"):
        try:
            header_date = parsedate_to_datetime(headers["date"]).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    received_at = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, timezone.utc).isoformat()
    return {
        "account_id": account_id, "message_id": message["id"], "provider": "gmail",
        "thread_id": message.get("threadId") or message["id"],
        "rfc_message_id": headers.get("message-id"), "subject": headers.get("subject") or "(No subject)",
        "sender_name": sender_name, "sender_address": sender_address,
        "to_json": [address.lower() for _, address in getaddresses([headers.get("to", "")]) if address],
        "cc_json": [address.lower() for _, address in getaddresses([headers.get("cc", "")]) if address],
        "bcc_json": [address.lower() for _, address in getaddresses([headers.get("bcc", "")]) if address],
        "direction": direction, "received_at": received_at, "header_date": header_date,
        "labels_json": labels, "body_text": body, "attachments_json": attachments,
        "has_attachments": int(bool(attachments)),
    }
