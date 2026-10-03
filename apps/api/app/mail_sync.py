"""Small resumable mailbox importer for the first local connected-data release."""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import random
import re
from datetime import datetime, timedelta, timezone, time
from html import unescape
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .connectors import ConnectorService, ConnectionError as ProviderConnectionError
from .mail_index import normalize_gmail_message
from .repository import Repository


def months_ago(months: int) -> datetime:
    now = datetime.now(timezone.utc)
    month_index = now.year * 12 + now.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1]))


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
        backfill = account["provider"] == "gmail" and self.repository.needs_gmail_backfill(account_id)
        resuming = bool(previous and previous["status"] in {"running", "failed"})
        cursor = previous["page_token"] if resuming and not backfill else None
        if resuming and previous["cutoff_at"]:
            cutoff_at = previous["cutoff_at"]
        else:
            # A completed scan only guarantees coverage through its start time:
            # mail arriving while pages were fetched must appear in the next scan.
            last_covered = None if backfill else previous["started_at"] if previous and previous["status"] == "complete" else account["last_synced_at"]
            cutoff = (datetime.fromisoformat(last_covered).astimezone(timezone.utc) - timedelta(minutes=5)
                      if last_covered else months_ago(preferences["history_months"]))
            cutoff_at = cutoff.isoformat()
        self.repository.start_sync_job(account_id, cutoff_at)
        try:
            token = await self.connectors.access_token(account)
            if account["provider"] == "gmail":
                if backfill:
                    account = {**account, "gmail_history_id": None}
                await self._gmail(account, preferences, token, cursor, cutoff_at)
            else:
                await self._outlook(account, preferences, token, cursor, cutoff_at)
            self.repository.update_sync_job(account_id, "complete")
        except (httpx.HTTPError, ValueError, KeyError, RuntimeError, ProviderConnectionError) as exc:
            # Keep the cursor already saved after the last successful page.
            saved = self.repository.get_sync_job(account_id)
            self.repository.update_sync_job(account_id, "failed", saved["page_token"] if saved else None, error=str(exc)[:240])
        finally:
            self._running.discard(account_id)

    async def _gmail(self, account: dict, preferences: dict, token: str, cursor: str | None, cutoff_at: str) -> None:
        # Gmail accepts Unix seconds, avoiding the PST-midnight interpretation of dates.
        cutoff_seconds = int(datetime.fromisoformat(cutoff_at).timestamp())
        query = f"after:{cutoff_seconds} -in:spam -in:trash -in:drafts"
        if not preferences["include_sent"]:
            query += " -in:sent"
        headers = {"Authorization": f"Bearer {token}"}
        position = json.loads(cursor) if cursor and cursor.startswith("{") else {"page_token": cursor, "offset": 0}
        consecutive_inaccessible = 0
        async with httpx.AsyncClient(timeout=30) as client:
            if account.get("gmail_history_id") and not cursor:
                try:
                    await self._gmail_history(client, account, headers, account["gmail_history_id"], preferences["include_sent"])
                    return
                except GmailRequestError as exc:
                    if exc.status != 404:
                        raise
                    # Expired history requires a fresh scan of the selected import window.
                    cutoff_at = months_ago(preferences["history_months"]).isoformat()
                    self.repository.set_sync_cutoff(account["id"], cutoff_at)
                    cutoff_seconds = int(datetime.fromisoformat(cutoff_at).timestamp())
                    query = f"after:{cutoff_seconds} -in:spam -in:trash -in:drafts"
                    if not preferences["include_sent"]:
                        query += " -in:sent"
            job = self.repository.get_sync_job(account["id"])
            starting_history = job.get("initial_history_id") if job else None
            scan_marker = job["started_at"] if job else datetime.now(timezone.utc).isoformat()
            if not starting_history:
                profile = await self._gmail_get(client, account, "https://gmail.googleapis.com/gmail/v1/users/me/profile", headers)
                starting_history = profile.json()["historyId"]
                self.repository.set_sync_initial_history_id(account["id"], starting_history)
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
                    self._save_gmail_message(account, detail.json(), scan_marker)
                    self.repository.update_sync_job(account["id"], "running", message_cursor, 1)
                    await asyncio.sleep(0.25)
                position = {"page_token": page.get("nextPageToken"), "offset": 0}
                self.repository.update_sync_job(account["id"], "running", position["page_token"])
                if not position["page_token"]:
                    self.repository.reconcile_full_gmail_scan(account["id"], scan_marker, cutoff_at, preferences["include_sent"])
                    await self._gmail_history(client, account, headers, starting_history, preferences["include_sent"])
                    self.repository.mark_mail_index_backfilled(account["id"])
                    return

    def _save_gmail_message(self, account: dict, message: dict, seen_sync_at: str | None = None) -> None:
        normalized = normalize_gmail_message(message, account["id"], account["email"])
        self.repository.upsert_mail_message(normalized, seen_sync_at)
        snippet = re.sub(r"\s+", " ", normalized["body_text"] or message.get("snippet", "")).strip()[:1800]
        labels = message.get("labelIds", [])
        folder = "sent" if "SENT" in labels else "inbox" if "INBOX" in labels else "archive"
        self.repository.upsert_mail_source(account["id"], "gmail", message["id"], normalized["subject"][:300],
            snippet, normalized["received_at"], normalized["sender_address"][:300], folder)
        self._maybe_action(account, message["id"], normalized["subject"][:300], snippet, normalized["received_at"])

    async def _gmail_history(self, client: httpx.AsyncClient, account: dict, headers: dict[str, str], start_id: str,
                             include_sent: bool) -> None:
        page_token = None
        latest_history = start_id
        while True:
            params = {"startHistoryId": start_id, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            response = await self._gmail_get(client, account, "https://gmail.googleapis.com/gmail/v1/users/me/history", headers, params)
            page = response.json()
            latest_history = page.get("historyId", latest_history)
            changed: set[str] = set()
            deleted: set[str] = set()
            for event in page.get("history", []):
                changed.update(entry["message"]["id"] for key in ("messagesAdded", "labelsAdded", "labelsRemoved")
                               for entry in event.get(key, []) if entry.get("message", {}).get("id"))
                deleted.update(entry["message"]["id"] for entry in event.get("messagesDeleted", [])
                               if entry.get("message", {}).get("id"))
            for message_id in deleted:
                self.repository.delete_mail_message(account["id"], message_id)
            for message_id in changed - deleted:
                try:
                    detail = await self._gmail_get(client, account,
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(message_id, safe='')}", headers,
                        {"format": "full"})
                except GmailRequestError as exc:
                    if exc.status == 404:
                        self.repository.delete_mail_message(account["id"], message_id)
                        continue
                    raise
                message = detail.json()
                if any(label in message.get("labelIds", []) for label in ("TRASH", "SPAM", "DRAFT")) or not include_sent and "SENT" in message.get("labelIds", []):
                    self.repository.delete_mail_message(account["id"], message_id)
                else:
                    self._save_gmail_message(account, message)
            self.repository.update_sync_job(account["id"], "running", increment=len(changed))
            page_token = page.get("nextPageToken")
            if not page_token:
                self.repository.set_gmail_history_id(account["id"], latest_history)
                return

    async def _outlook(self, account: dict, preferences: dict, token: str, cursor: str | None, cutoff_at: str) -> None:
        cutoff = cutoff_at.replace("+00:00", "Z")
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
                if account["provider"] == "gmail" and self.repository.needs_gmail_backfill(account["id"]):
                    due = True
                if job and job["status"] == "running":
                    due = True  # Resume a job left running when the API process restarted.
                elif job and job["status"] == "failed":
                    transient = any(marker in (job["error"] or "") for marker in ("rateLimitExceeded", "quotaExceeded", "Gmail returned 429", "Gmail returned 5", "Client error '403 Forbidden'"))
                    due = transient and (datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])).total_seconds() >= 300
                if due:
                    asyncio.create_task(self.run(account["id"]))
            await asyncio.sleep(60)
