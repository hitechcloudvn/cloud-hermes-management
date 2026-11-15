"""Login/logout + user-account management routes. / Route đăng nhập/đăng xuất + quản lý user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ..auth import SESSION_COOKIE, UserStore, create_session
from ..config import Settings, get_settings
from ..deps import current_session_user, get_limiter, require_auth
from ..models import ChangePasswordRequest, CreateUserRequest, LoginRequest, fail, ok

router = APIRouter(prefix="/api/auth", tags=["auth"])

BEARER_PRINCIPAL = "root"
FALLBACK_ADMIN = "admin"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Any:
    """Verify password (bcrypt) and set the session cookie. / Kiểm tra mật khẩu và đặt cookie phiên."""
    ip = _client_ip(request)
    limiter = get_limiter()
    limiter.check(ip)
    store = UserStore(settings)
    if not store.verify(body.username, body.password):
        limiter.record_failure(ip)
        return fail("invalid username or password", 401)
    limiter.reset(ip)
    token = create_session(body.username, settings.hermes_mgmt_session_secret)
    payload = ok({"username": body.username})
    _set_cookie(payload, token)
    return payload


@router.post("/logout")
async def logout() -> Any:
    """Idempotent logout; clears the session cookie. / Đăng xuất idempotent; xóa cookie phiên."""
    payload = ok({"logged_out": True})
    payload.delete_cookie(SESSION_COOKIE)
    return payload


@router.get("/user")
async def current_user(principal: str = Depends(require_auth)) -> Any:
    """Current authenticated principal (bearer -> root). / Principal hiện tại (bearer -> root)."""
    return ok({"username": principal})


@router.post("/create-user")
async def create_user(
    body: CreateUserRequest,
    principal: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Create an additional admin user. / Tạo thêm user admin."""
    store = UserStore(settings)
    try:
        store.add_user(body.username, body.password)
    except ValueError:
        return fail(f"user already exists: {body.username}", 409)
    return ok({"username": body.username, "created": True})


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    principal: str = Depends(require_auth),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Rotate the password of the current user. / Đổi mật khẩu của user hiện tại."""
    target = FALLBACK_ADMIN if principal == BEARER_PRINCIPAL else principal
    store = UserStore(settings)
    if not store.verify(target, body.old_password):
        return fail("old password is incorrect", 400)
    store.change_password(target, body.old_password, body.new_password)
    return ok({"username": target, "changed": True})


@router.delete("/user")
async def delete_user(
    user: str = Depends(current_session_user),
    settings: Settings = Depends(get_settings),
) -> Any:
    """Remove the current session user's account. / Xóa tài khoản user của phiên hiện tại."""
    store = UserStore(settings)
    if not store.delete_user(user):
        return fail(f"user not found: {user}", 404)
    return ok({"username": user, "deleted": True})
