"""Simple token-based authentication for nanobot web UI."""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path


class AuthManager:
    """File-backed user store with token authentication.

    Users are stored as ``{username: {password_hash, salt, token}}`` in a
    JSON file under the nanobot data directory.
    """

    def __init__(self, store_path: Path, invite_code: str = ""):
        self.store_path = store_path
        self.invite_code = invite_code
        self._users: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, username: str, password: str, invite_code: str) -> str | None:
        """Register a new user. Returns a token on success, None on failure."""
        if self.invite_code and invite_code != self.invite_code:
            return None
        if username in self._users:
            return None
        if not username or not password:
            return None

        salt = secrets.token_hex(16)
        pw_hash = self._hash(password, salt)
        token = secrets.token_hex(32)
        self._users[username] = {"password_hash": pw_hash, "salt": salt, "token": token}
        self._save()
        return token

    def login(self, username: str, password: str) -> str | None:
        """Authenticate a user. Returns a token on success, None on failure."""
        user = self._users.get(username)
        if not user:
            return None
        if self._hash(password, user["salt"]) != user["password_hash"]:
            return None
        # Rotate token on each login
        token = secrets.token_hex(32)
        user["token"] = token
        self._save()
        return token

    def verify_token(self, token: str) -> str | None:
        """Return the username for a valid token, or None."""
        if not token:
            return None
        for username, data in self._users.items():
            if data.get("token") == token:
                return username
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        return hashlib.sha256((salt + password).encode()).hexdigest()

    def _load(self):
        if self.store_path.exists():
            try:
                self._users = json.loads(self.store_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._users = {}
        else:
            self._users = {}

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(json.dumps(self._users, indent=2), encoding="utf-8")
