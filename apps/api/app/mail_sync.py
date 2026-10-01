"""Small resumable mailbox importer for the first local connected-data release."""

from __future__ import annotations

import asyncio
import base64
import calendar
import hashlib
import json
import random
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


class GmailRequestError(RuntimeError):
    def __init__(self, status: int, reason: str, message: str) -> None:
        self.status = status
        self.reason = reason
        super().__init__(f"Gmail returned {status}{f' ({reason})' if reason else ''}: {message}")


class MailSync:
    def __init__(self, repository: Repository, connectors: ConnectorService) -> None:
        self.repository = repository
        self.connectors = connectors
        self._running: set[str] = set()

    async def _gmail_get(self, client: httpx.AsyncClient, account: dict, url: str, headers: dict[str, str], params: dict | None = None) -> httpx.Response:
        refreshed = False
        for attempt in range(10):
            try:
                response = await client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 9:
                    raise
                await asyncio.sleep(min(60, 2 ** attempt) + random.uniform(0, 1))
                continue
            if response.status_code == 401 and not refreshed:
                headers["Authorization"] = f"Bearer {await self.connectors.access_token(account)}"
                refreshed = True
                continue
            if response.status_code < 400:
                return response
            try:
                problem = response.json().get("error", {})
                reason = (problem.get("errors") or [{}])[0].get("reason", "")
                message = problem.get("message", response.reason_phrase)
            except (ValueError, AttributeError, TypeError):
                reason, message = "", response.reason_phrase
            retryable = response.status_code in {429, 500, 502, 503, 504} or response.status_code == 403 and reason in {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}
            if retryable and attempt < 9:
                retry_after = response.headers.get("Retry-After", "")
                delay = min(60, 2 ** attempt) + random.uniform(0, 1)
                if retry_after.isdigit():
                    delay = max(delay, min(120, int(retry_after)))
                await asyncio.sleep(delay)
                continue
            raise GmailRequestError(response.status_code, reason, message)
        raise RuntimeError("Gmail did not respond after retries")

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
        position = json.loads(cursor) if cursor and cursor.startswith("{") else {"page_token": cursor, "offset": 0}
        consecutive_inaccessible = 0
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = {"q": query, "maxResults": 100}
                if position["page_token"]:
                    params["pageToken"] = position["page_token"]
                response = await self._gmail_get(client, account, "https://gmail.googleapis.com/gmail/v1/users/me/messages", headers, params)
                page = response.json()
                if position["page_token"] is None and position["offset"] == 0:
                    self.repository.update_sync_job(account["id"], "running", cursor, total_estimate=page.get("resultSizeEstimate"))
                for index, item in enumerate(page.get("messages", [])[position["offset"]:], start=position["offset"]):
                    message_cursor = json.dumps({"page_token": position["page_token"], "offset": index + 1})
                    try:
                        detail = await self._gmail_get(client, account, f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(item['id'], safe='')}", headers, {"format": "full"})
                    except GmailRequestError as exc:
                        if exc.status not in {403, 404} or exc.status == 403 and exc.reason not in {"", "forbidden", "notFound"}:
                            raise
                        consecutive_inaccessible += 1
                        if consecutive_inaccessible > 5:
                            raise RuntimeError("Google denied several messages in a row. Check Gmail access and retry the import") from exc
                        self.repository.update_sync_job(account["id"], "running", message_cursor, skipped=1)
                        continue
                    consecutive_inaccessible = 0
                    message = detail.json()
                    fields = {entry["name"].lower(): entry["value"] for entry in message.get("payload", {}).get("headers", [])}
                    title = str(make_header(decode_header(fields.get("subject", "(No subject)"))))
                    body = gmail_text(message.get("payload", {})) or message.get("snippet", "")
                    snippet = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", body))).strip()[:1800]
                    sent_at = datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, timezone.utc).isoformat()
                    folder = "sent" if "SENT" in message.get("labelIds", []) else "inbox" if "INBOX" in message.get("labelIds", []) else "archive"
                    self.repository.upsert_mail_source(account["id"], "gmail", item["id"], title[:300], snippet, sent_at, fields.get("from", "")[:300], folder)
                    self._maybe_action(account, item["id"], title[:300], snippet, sent_at)
                    self.repository.update_sync_job(account["id"], "running", message_cursor, 1)
                    await asyncio.sleep(0.25)
                position = {"page_token": page.get("nextPageToken"), "offset": 0}
                self.repository.update_sync_job(account["id"], "running", position["page_token"])
                if not position["page_token"]:
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
                if job and job["status"] == "running":
                    due = True  # Resume a job left running when the API process restarted.
                elif job and job["status"] == "failed":
                    transient = any(marker in (job["error"] or "") for marker in ("rateLimitExceeded", "quotaExceeded", "Gmail returned 429", "Gmail returned 5", "Client error '403 Forbidden'"))
                    due = transient and (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])).total_seconds() >= 300
                if due:
                    asyncio.create_task(self.run(account["id"]))
            await asyncio.sleep(60)
