"""Device-local encryption for provider credentials.

The key and encrypted values stay in the data directory. The key file is
created with owner-only permissions on systems that support POSIX modes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
import keyring
from keyring.errors import KeyringError


class CredentialVault:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.key_path = data_dir / "vault.key"
        self.values_path = data_dir / "credentials.enc.json"
        self._lock = Lock()

    def _cipher(self) -> Fernet:
        if os.name == "nt":
            try:
                account = str(self.data_dir.resolve())
                saved = keyring.get_password("Hey Broski vault", account)
                if not saved:
                    saved = Fernet.generate_key().decode("ascii")
                    keyring.set_password("Hey Broski vault", account, saved)
                return Fernet(saved.encode("ascii"))
            except KeyringError:
                # Portable fallback for environments without an OS credential backend.
                pass
        if not self.key_path.exists():
            key = Fernet.generate_key()
            try:
                descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key)
        return Fernet(self.key_path.read_bytes())

    def _read(self) -> dict[str, str]:
        if not self.values_path.exists():
            return {}
        try:
            return json.loads(self.values_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("The local credential vault could not be read") from exc

    def get(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            encrypted = self._read().get(name)
            if not encrypted:
                return None
            try:
                return json.loads(self._cipher().decrypt(encrypted.encode("ascii")))
            except (InvalidToken, ValueError) as exc:
                raise RuntimeError("The local credential vault could not be decrypted") from exc

    def put(self, name: str, value: dict[str, Any]) -> None:
        with self._lock:
            values = self._read()
            values[name] = self._cipher().encrypt(json.dumps(value).encode("utf-8")).decode("ascii")
            temporary = self.values_path.with_suffix(".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(values, handle)
            temporary.replace(self.values_path)

    def delete(self, name: str) -> None:
        with self._lock:
            values = self._read()
            if name in values:
                del values[name]
                temporary = self.values_path.with_suffix(".tmp")
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(values, handle)
                temporary.replace(self.values_path)
