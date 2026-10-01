"""Small resumable mailbox importer for the first local connected-data release."""

from __future__ import annotations

import asyncio
import base64
import calendar
import hashlib
import json
import re
from datetime import datetime, timezone, time
from email.header import decode_header, make_header
from html import unescape
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .connectors import ConnectorService, ConnectionError as ProviderConnectionError
from .repository import Repository


def months_ago(months: int) -> datetime:
    now = datetime.now(timezone.utc)
    month_index = now.year * 12 + now.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1]))


def gmail_text(payload: dict) -> str:
    stack = [payload]
    while stack:
        part = stack.pop(0)
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            encoded = part["body"]["data"]
            return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8", errors="replace")[:3000]
        stack.extend(part.get("parts", []))
    return ""


class MailSync:
    def __init__(self, repository: Repository, connectors: ConnectorService) -> None:
        self.repository = repository
        self.connectors = connectors
        self._running: set[str] = set()

    def _maybe_action(self, account: dict, message_id: str, title: str, snippet: str, sent_at: str) -> None:
        """Create a conservative reminder only for an explicit dated obligation."""
        if not re.search(r"\b(due|renew(?:s|al)?|expir(?:es|y|ation)?)\b", f"{title} {snippet}", re.I):
            return
        match = re.search(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", snippet, re.I)
        if not match:
            return
        try:
            due_date = datetime.strptime(match.group(0), "%d %B %Y").date()
        except ValueError:
            return
        zone_name = (self.repository.get_profile() or {}).get("time_zone", "UTC")
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone = timezone.utc
        today = datetime.now(zone).date()
        if abs((due_date - today).days) > 365:
            return
        due_at = datetime.combine(due_date, time(18, 0), tzinfo=zone).astimezone(timezone.utc).isoformat()
        identifier = hashlib.sha256(f"{account['id']}:{message_id}".encode()).hexdigest()[:24]
        source = {"source_type": "email", "source_id": f"{account['id']}:{message_id}",
                  "account_label": f"{account['provider'].title()} / {account['email']}", "title": title,
                  "snippet": snippet, "timestamp": sent_at}
        self.repository.upsert_action({"id": f"action_mail_{identifier}", "session_id": None, "card_type": "deadline",
            "title": f"Review: {title[:100]}", "description": f"This message mentions a due or renewal date of {due_date.isoformat()}.",
            "priority": "urgent" if due_date <= today else "high" if (due_date - today).days <= 3 else "medium",
            "status": "pending", "due_at": due_at, "confidence": 0.75, "sources": [source],
            "proposed_action": {"tool": "reminders.create", "requires_approval": True, "input": {"title": title[:100], "due_at": due_at}}})

    async def run(self, account_id: str) -> None:
        if account_id in self._running:
            return
        account = self.repository.get_account(account_id)
        preferences = self.repository.get_sync_preferences(account_id)
        if not account or not preferences:
            return
        self._running.add(account_id)
        previous = self.repository.get_sync_job(account_id)
        cursor = previous["page_token"] if previous and previous["status"] in {"running", "failed"} else None
        self.repository.start_sync_job(account_id)
        try:
            token = await self.connectors.access_token(account)
            if account["provider"] == "gmail":
                await self._gmail(account, preferences, token, cursor)
            else:
                await self._outlook(account, preferences, token, cursor)
            self.repository.update_sync_job(account_id, "complete")
        except (httpx.HTTPError, ValueError, KeyError, RuntimeError, ProviderConnectionError) as exc:
            # Keep the cursor already saved after the last successful page.
            saved = self.repository.get_sync_job(account_id)
            self.repository.update_sync_job(account_id, "failed", saved["page_token"] if saved else None, error=str(exc)[:240])
        finally:
            self._running.discard(account_id)

    async def _gmail(self, account: dict, preferences: dict, token: str, cursor: str | None) -> None:
        cutoff = months_ago(preferences["history_months"]).strftime("%Y/%m/%d")
        query = f"after:{cutoff} -in:spam -in:trash"
        if not preferences["include_sent"]:
            query += " in:inbox"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {"q": query, "maxResults": 50}
                if cursor:
                    params["pageToken"] = cursor
                response = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params=params, headers=headers)
                response.raise_for_status()
                page = response.json()
                count = 0
                for item in page.get("messages", []):
                    detail = await client.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(item['id'], safe='')}", params={"format": "full"}, headers=headers)
                    detail.raise_for_status()
                    message = detail.json()
                    fields = {entry["name"].lower(): entry["value"] for entry in message.get("payload", {}).get("headers", [])}
                    title = str(make_header(decode_header(fields.get("subject", "(No subject)"))))
                    body = gmail_text(message.get("payload", {})) or message.get("snippet", "")
                    snippet = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", body))).strip()[:1800]
                    sent_at = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, timezone.utc).isoformat()
                    folder = "sent" if "SENT" in message.get("labelIds", []) else "inbox" if "INBOX" in message.get("labelIds", []) else "archive"
                    self.repository.upsert_mail_source(account["id"], "gmail", item["id"], title[:300], snippet, sent_at, fields.get("from", "")[:300], folder)
                    self._maybe_action(account, item["id"], title[:300], snippet, sent_at)
                    count += 1
                cursor = page.get("nextPageToken")
                self.repository.update_sync_job(account["id"], "running", cursor, count)
                if not cursor:
                    return

    async def _outlook(self, account: dict, preferences: dict, token: str, cursor: str | None) -> None:
        cutoff = months_ago(preferences["history_months"]).isoformat().replace("+00:00", "Z")
        folders = ["inbox"] + (["sentitems"] if preferences["include_sent"] else [])
        position = json.loads(cursor) if cursor else {"folder": folders[0], "url": None}
        headers = {"Authorization": f"Bearer {token}", "Prefer": 'outlook.body-content-type="text"'}
        async with httpx.AsyncClient(timeout=30) as client:
            for folder in folders[folders.index(position["folder"]):]:
                url = position.get("url") if folder == position["folder"] else None
                while True:
                    if url:
                        if not url.startswith("https://graph.microsoft.com/v1.0/"):
                            raise ValueError("Invalid Microsoft pagination URL")
                        response = await client.get(url, headers=headers)
                    else:
                        field = "sentDateTime" if folder == "sentitems" else "receivedDateTime"
                        response = await client.get(f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages",
                            params={"$top": 50, "$select": "id,subject,body,bodyPreview,from,receivedDateTime,sentDateTime", "$filter": f"{field} ge {cutoff}"}, headers=headers)
                    response.raise_for_status()
                    page = response.json()
                    count = 0
                    for message in page.get("value", []):
                        sender = ((message.get("from") or {}).get("emailAddress") or {}).get("address", "")
                        sent_at = message.get("sentDateTime") if folder == "sentitems" else message.get("receivedDateTime")
                        content = (message.get("body") or {}).get("content") or message.get("bodyPreview") or ""
                        snippet = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", content))).strip()[:1800]
                        self.repository.upsert_mail_source(account["id"], "outlook", message["id"], (message.get("subject") or "(No subject)")[:300],
                            snippet, sent_at or datetime.now(timezone.utc).isoformat(), sender[:300], folder)
                        self._maybe_action(account, message["id"], (message.get("subject") or "(No subject)")[:300], snippet, sent_at or datetime.now(timezone.utc).isoformat())
                        count += 1
                    url = page.get("@odata.nextLink")
                    next_folder = folder if url else (folders[folders.index(folder)+1] if folders.index(folder)+1 < len(folders) else None)
                    next_cursor = json.dumps({"folder": next_folder, "url": url}) if next_folder else None
                    self.repository.update_sync_job(account["id"], "running", next_cursor, count)
                    if not url:
                        break

    async def scheduler(self) -> None:
        while True:
            for account in self.repository.list_accounts():
                preferences = self.repository.get_sync_preferences(account["id"])
                if not preferences or account["id"] in self._running:
                    continue
                job = self.repository.get_sync_job(account["id"])
                due = not account["last_synced_at"] or (datetime.now(timezone.utc) - datetime.fromisoformat(account["last_synced_at"])).total_seconds() >= preferences["interval_hours"] * 3600
                if job and job["status"] == "failed":
                    due = False  # explicit retry after a connection or provider error
                if due:
                    asyncio.create_task(self.run(account["id"]))
            await asyncio.sleep(60)
