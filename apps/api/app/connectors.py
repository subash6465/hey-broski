"""OAuth connection and small read-only verification requests."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from .credential_vault import CredentialVault
from .repository import Repository

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_CLIENT_AUTH_URIS = {GOOGLE_AUTH, "https://accounts.google.com/o/oauth2/auth"}
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
MICROSOFT_SCOPE = "offline_access User.Read Mail.Read"


class ConnectionError(Exception):
    pass


class ConnectorService:
    def __init__(self, repository: Repository, vault: CredentialVault) -> None:
        self.repository = repository
        self.vault = vault

    @staticmethod
    def redirect_uri(provider: str) -> str:
        name = "gmail" if provider == "gmail" else "outlook"
        configured = os.getenv("GOOGLE_REDIRECT_URI" if provider == "gmail" else "MICROSOFT_REDIRECT_URI")
        return configured or f"http://127.0.0.1:8000/api/accounts/{name}/callback"

    def import_gmail_client(self, payload: dict) -> None:
        installed = payload.get("installed")
        if not isinstance(installed, dict) or not isinstance(installed.get("client_id"), str):
            raise ConnectionError("Upload the Desktop OAuth client JSON downloaded from Google Cloud")
        if not installed["client_id"].endswith(".apps.googleusercontent.com"):
            raise ConnectionError("The Google OAuth client ID is invalid")
        if installed.get("auth_uri") not in (None, *GOOGLE_CLIENT_AUTH_URIS) or installed.get("token_uri") not in (None, GOOGLE_TOKEN):
            raise ConnectionError("The OAuth client does not use Google's standard authorization endpoints")
        self.vault.put("gmail_client", {"client_id": installed["client_id"], "client_secret": installed.get("client_secret", "")})

    def has_gmail_client(self) -> bool:
        return self.vault.get("gmail_client") is not None

    def import_outlook_client(self, client_id: str) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", client_id):
            raise ConnectionError("Enter the Application (client) ID from Microsoft Entra")
        self.vault.put("outlook_client", {"client_id": client_id})

    def has_outlook_client(self) -> bool:
        return bool(self.vault.get("outlook_client") or os.getenv("MICROSOFT_CLIENT_ID", "").strip())

    def _client_id(self, provider: str) -> str:
        if provider == "gmail":
            client = self.vault.get("gmail_client")
            if not client:
                raise ConnectionError("Import a Google Desktop OAuth client first")
            return client["client_id"]
        client_id = (self.vault.get("outlook_client") or {}).get("client_id") or os.getenv("MICROSOFT_CLIENT_ID", "").strip()
        if not client_id:
            raise ConnectionError("Microsoft connection is not configured yet. Set MICROSOFT_CLIENT_ID in the local environment")
        return client_id

    def start(self, provider: str) -> str:
        client_id = self._client_id(provider)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        self.repository.create_oauth_attempt(state, provider, verifier, expires)
        if provider == "gmail":
            params = {"client_id": client_id, "redirect_uri": self.redirect_uri(provider), "response_type": "code", "scope": GOOGLE_SCOPE,
                      "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
            return f"{GOOGLE_AUTH}?{urlencode(params)}"
        params = {"client_id": client_id, "redirect_uri": self.redirect_uri(provider), "response_type": "code", "response_mode": "query",
                  "scope": MICROSOFT_SCOPE, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

    async def finish(self, provider: str, state: str, code: str) -> dict:
        attempt = self.repository.consume_oauth_attempt(state, provider)
        if not attempt:
            raise ConnectionError("The connection request expired or its security state did not match. Try again")
        client_id = self._client_id(provider)
        token_url = GOOGLE_TOKEN if provider == "gmail" else "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        body = {"client_id": client_id, "code": code, "code_verifier": attempt["code_verifier"],
                "redirect_uri": self.redirect_uri(provider), "grant_type": "authorization_code"}
        if provider == "gmail":
            body["client_secret"] = (self.vault.get("gmail_client") or {}).get("client_secret", "")
        else:
            body["scope"] = MICROSOFT_SCOPE
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token_response = await client.post(token_url, data=body)
                token_response.raise_for_status()
                tokens = token_response.json()
                access_token = tokens["access_token"]
                headers = {"Authorization": f"Bearer {access_token}"}
                if provider == "gmail":
                    profile = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers)
                    profile.raise_for_status()
                    # A mailbox read confirms the requested Gmail scope works.
                    probe = await client.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"maxResults": 1}, headers=headers)
                    probe.raise_for_status()
                    email = profile.json()["emailAddress"]
                    display_name = email
                else:
                    profile = await client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
                    profile.raise_for_status()
                    probe = await client.get("https://graph.microsoft.com/v1.0/me/messages", params={"$top": 1, "$select": "id"}, headers=headers)
                    probe.raise_for_status()
                    data = profile.json()
                    email = data.get("mail") or data.get("userPrincipalName")
                    display_name = data.get("displayName") or email
                if not email:
                    raise ConnectionError("The provider did not return a mailbox address")
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ConnectionError("Sign-in completed, but Hey Broski could not read this mailbox. Check the API and permissions, then retry") from exc
        existing_account = next((item for item in self.repository.list_accounts() if item["provider"] == provider and item["email"] == email.lower()), None)
        previous_tokens = self.vault.get(f"account:{existing_account['id']}") if existing_account else None
        tokens["refresh_token"] = tokens.get("refresh_token") or (previous_tokens or {}).get("refresh_token")
        if not tokens["refresh_token"]:
            raise ConnectionError("The provider did not grant offline access. Reconnect and approve the requested permissions")
        account = self.repository.upsert_account(provider, email, display_name)
        try:
            self.vault.put(f"account:{account['id']}", tokens)
        except (OSError, RuntimeError) as exc:
            if not existing_account:
                self.repository.delete_account(account["id"])
            raise ConnectionError("The local credential vault could not save this account") from exc
        return account

    async def access_token(self, account: dict) -> str:
        tokens = self.vault.get(f"account:{account['id']}")
        if not tokens:
            raise ConnectionError("This account has no local credentials. Reconnect it")
        # Refresh before every sync. Provider refresh tokens may rotate.
        provider = account["provider"]
        body = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": self._client_id(provider)}
        if provider == "gmail":
            body["client_secret"] = (self.vault.get("gmail_client") or {}).get("client_secret", "")
            url = GOOGLE_TOKEN
        else:
            body["scope"] = MICROSOFT_SCOPE
            url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, data=body)
                response.raise_for_status()
                updated = response.json()
                tokens.update(updated)
                self.vault.put(f"account:{account['id']}", tokens)
                return tokens["access_token"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ConnectionError("The account authorization expired. Reconnect this mailbox") from exc
