"""bcrypt password hashing + HMAC session tokens + Bearer compare. / Mã hóa mật khẩu + phiên HMAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import bcrypt

from .config import Settings
from .env_file import get_env_value

BCRYPT_COST = 12
SESSION_COOKIE = "hermes_mgmt_session"
SESSION_TTL_SECONDS = 7 * 24 * 3600
FALLBACK_ADMIN = "admin"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt cost 12. / Băm mật khẩu bằng bcrypt cost 12."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_COST)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish bcrypt verification. / Kiểm tra mật khẩu bằng bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def bearer_matches(presented: str, expected: str) -> bool:
    """Compare bearer tokens in constant time. / So sánh token bearer theo thời gian không đổi."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented, expected)


def create_session(username: str, secret: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Create an HMAC-signed session token. / Tạo token phiên có chữ ký HMAC."""
    expiry = int(time.time()) + ttl_seconds
    payload = f"{username}:{expiry}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{encoded}.{signature}"


def validate_session(token: str, secret: str) -> str | None:
    """Return the session username when the token is valid. / Trả về tên user nếu token hợp lệ."""
    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        username, expiry_s = payload.rsplit(":", 1)
        expiry = int(expiry_s)
    except (ValueError, TypeError):
        return None
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    if time.time() > expiry:
        return None
    return username


class UserStore:
    """JSON file of admin users with bcrypt hashes. / File JSON chứa user admin + hash bcrypt."""

    def __init__(self, settings: Settings) -> None:
        self._path: Path = settings.users_file
        self._settings = settings

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}

    def _save(self, users: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(users, indent=2), encoding="utf-8")

    def list_users(self) -> list[str]:
        users = self._load()
        names = set(users)
        if self._fallback_hash() is not None:
            names.add(FALLBACK_ADMIN)
        return sorted(names)

    def _fallback_hash(self) -> str | None:
        value = get_env_value(self._settings.mgmt_env_file, "HERMES_MGMT_PASSWORD_HASH")
        return value or None

    def add_user(self, username: str, password: str) -> None:
        """Create a user; raises ValueError when it exists. / Tạo user; ValueError nếu đã tồn tại."""
        users = self._load()
        if username in users:
            raise ValueError(f"user already exists: {username}")
        users[username] = hash_password(password)
        self._save(users)

    def verify(self, username: str, password: str) -> bool:
        users = self._load()
        stored = users.get(username)
        if stored is None and username == FALLBACK_ADMIN:
            fallback = self._fallback_hash()
            if fallback:
                return verify_password(password, fallback)
            return False
        if stored is None:
            return False
        return verify_password(password, stored)

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        if not self.verify(username, old_password):
            return False
        users = self._load()
        if username not in users:
            # Promote the fallback admin into the store once the password rotates. / Đưa admin dự phòng vào store khi đổi mật khẩu.
            users[username] = hash_password(new_password)
        else:
            users[username] = hash_password(new_password)
        self._save(users)
        return True

    def delete_user(self, username: str) -> bool:
        users = self._load()
        if username not in users:
            return False
        del users[username]
        self._save(users)
        return True
