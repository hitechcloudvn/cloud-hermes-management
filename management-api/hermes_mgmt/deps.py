"""FastAPI dependencies: require_auth + failure rate limiter. / Dependency: require_auth + giới hạn tần suất."""

from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request

from .auth import SESSION_COOKIE, UserStore, bearer_matches, validate_session
from .config import Settings, get_settings

RATE_LIMIT_MAX_FAILURES = 10
RATE_LIMIT_WINDOW_SECONDS = 15 * 60


class AuthRateLimiter:
    """In-process failed-auth counter per IP. / Bộ đếm lỗi xác thực theo IP trong tiến trình."""

    def __init__(self, max_failures: int = RATE_LIMIT_MAX_FAILURES, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}

    def _prune(self, ip: str) -> list[float]:
        now = time.monotonic()
        kept = [ts for ts in self._failures.get(ip, []) if now - ts < self.window_seconds]
        if kept:
            self._failures[ip] = kept
        else:
            self._failures.pop(ip, None)
        return kept

    def check(self, ip: str) -> None:
        """Raise 429 when the IP exceeded the failure budget. / Ném 429 khi IP vượt ngân sách lỗi."""
        if len(self._prune(ip)) >= self.max_failures:
            raise HTTPException(status_code=429, detail="too many failed authentication attempts")

    def record_failure(self, ip: str) -> None:
        self._failures.setdefault(ip, []).append(time.monotonic())
        self._prune(ip)

    def reset(self, ip: str) -> None:
        self._failures.pop(ip, None)

    def failure_count(self, ip: str) -> int:
        return len(self._prune(ip))


_limiter = AuthRateLimiter()


def get_limiter() -> AuthRateLimiter:
    """Shared rate limiter instance. / Thể hiện limiter dùng chung."""
    return _limiter


def reset_limiter() -> None:
    """Clear all failure counters (tests). / Xóa bộ đếm lỗi (cho tests)."""
    global _limiter
    _limiter = AuthRateLimiter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def require_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """Accept Bearer key or session cookie; returns the principal. / Chấp nhận Bearer hoặc cookie phiên."""
    ip = _client_ip(request)
    limiter = get_limiter()
    limiter.check(ip)

    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[len("Bearer ") :].strip()
        if bearer_matches(token, settings.hermes_mgmt_api_key):
            limiter.reset(ip)
            return "root"

    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        username = validate_session(cookie, settings.hermes_mgmt_session_secret)
        if username:
            limiter.reset(ip)
            return username

    limiter.record_failure(ip)
    raise HTTPException(status_code=401, detail="invalid or missing credentials")


def current_session_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """Require cookie-based session auth (for user-account routes). / Yêu cầu phiên cookie (cho route quản lý user)."""
    cookie = request.cookies.get(SESSION_COOKIE, "")
    if cookie:
        username = validate_session(cookie, settings.hermes_mgmt_session_secret)
        if username:
            return username
    raise HTTPException(status_code=401, detail="session required")


__all__ = [
    "require_auth",
    "current_session_user",
    "get_limiter",
    "reset_limiter",
    "AuthRateLimiter",
    "UserStore",
]
