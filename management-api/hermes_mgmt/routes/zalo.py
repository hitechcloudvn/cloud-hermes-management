"""Zalo personal-connect proxy to the local Node sidecar (127.0.0.1:3838). / Proxy Zalo tới sidecar Node cục bộ."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from .. import systemd_ctl
from ..config import Settings, get_settings
from ..env_file import delete_env_value, get_env_value, set_env_value
from ..models import ZaloSetOwnerRequest, fail, ok

router = APIRouter(prefix="/api/zalo", tags=["zalo"])


async def _sidecar_request(settings: Settings, method: str, path: str, **kwargs: Any) -> httpx.Response:
    """One request against the Zalo sidecar. / Một request tới sidecar Zalo."""
    async with httpx.AsyncClient(base_url=settings.zalo_sidecar_url, timeout=15.0) as client:
        return await client.request(method, path, **kwargs)


async def _safe_request(settings: Settings, method: str, path: str, **kwargs: Any) -> httpx.Response | None:
    """Request that returns None when the sidecar is down. / Trả về None nếu sidecar chết."""
    try:
        return await _sidecar_request(settings, method, path, **kwargs)
    except httpx.HTTPError:
        return None


def _sidecar_down() -> Any:
    return fail("zalo sidecar unavailable", 503)


@router.get("/status")
async def zalo_status(settings: Settings = Depends(get_settings)) -> Any:
    """Bot login status + owner configuration state. / Trạng thái đăng nhập bot + cấu hình owner."""
    response = await _safe_request(settings, "GET", "/status")
    owner_uid = get_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID") or ""
    payload: dict[str, Any] = {
        "status": "disconnected",
        "bot_uid": None,
        "name": None,
        "sidecar": response is not None,
        "owner_set": bool(owner_uid),
    }
    if response is not None and response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict):
            payload["status"] = data.get("status", payload["status"])
            payload["bot_uid"] = data.get("bot_uid") or data.get("uid")
            payload["name"] = data.get("name")
            if payload["status"] == "connected" and not payload["bot_uid"]:
                payload["bot_uid"] = data.get("uid")
    elif response is None:
        payload["status"] = "error"
    return ok(payload)


@router.post("/connect")
async def zalo_connect(settings: Settings = Depends(get_settings)) -> Any:
    """Start QR login (spawns the sidecar if needed). / Bắt đầu đăng nhập QR."""
    response = await _safe_request(settings, "POST", "/login/qr")
    if response is None:
        return _sidecar_down()
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if data.get("status") == "connected" or data.get("bot_uid"):
        return ok({"status": "connected", "bot_uid": data.get("bot_uid") or data.get("uid")})
    return ok({"status": "pending", "qr_url": "/api/zalo/qr"})


@router.get("/qr")
async def zalo_qr(settings: Settings = Depends(get_settings)) -> Any:
    """Raw QR PNG bytes (404 while generating). / Ảnh PNG QR (404 khi chưa tạo xong)."""
    response = await _safe_request(settings, "GET", "/qr.png")
    if response is None:
        return _sidecar_down()
    if response.status_code == 404:
        return fail("qr not ready yet", 404)
    if response.status_code != 200:
        return fail(f"qr fetch failed: {response.status_code}", 502)
    return Response(content=response.content, media_type="image/png")


@router.post("/set-owner")
async def zalo_set_owner(body: ZaloSetOwnerRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Set the boss as owner by phone (resolved) or uid; enables plugin + restarts gateway. / Đặt sếp làm owner qua số điện thoại hoặc uid."""
    owner_uid = body.uid
    if body.phone and not owner_uid:
        response = await _safe_request(settings, "POST", "/users/by-phones", json={"phones": [body.phone]})
        if response is None:
            return _sidecar_down()
        if response.status_code == 409:
            return fail("bot is not logged in yet", 409)
        try:
            data = response.json()
        except ValueError:
            data = {}
        users = data.get("users") or data.get("data") or [] if isinstance(data, dict) else []
        resolved = None
        if isinstance(users, list):
            for item in users:
                if isinstance(item, dict) and item.get("uid"):
                    resolved = str(item["uid"])
                    break
        if not resolved:
            return fail(f"phone has no Zalo account: {body.phone}", 404)
        owner_uid = resolved
    if not owner_uid:
        return fail("either 'phone' or 'uid' is required", 422)
    # Confirm the bot session exists before wiring the owner. / Kiểm tra phiên bot trước khi gán owner.
    status_response = await _safe_request(settings, "GET", "/status")
    if status_response is None:
        return _sidecar_down()
    bot_logged_in = status_response.status_code == 200
    if bot_logged_in:
        try:
            status_data = status_response.json()
            bot_logged_in = bool(status_data.get("bot_uid") or status_data.get("uid")) or status_data.get("status") == "connected"
        except ValueError:
            bot_logged_in = True
    if not bot_logged_in:
        return fail("bot is not logged in yet", 409)
    set_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID", str(owner_uid))
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    return ok({"owner_uid": str(owner_uid), "owner_set": True})


@router.get("/owner")
async def zalo_owner(settings: Settings = Depends(get_settings)) -> Any:
    """Current owner uid + whether it is set. / UID owner hiện tại + đã cấu hình chưa."""
    owner_uid = get_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID") or ""
    return ok({"owner_uid": owner_uid or None, "owner_set": bool(owner_uid)})


@router.post("/disconnect")
async def zalo_disconnect(settings: Settings = Depends(get_settings)) -> Any:
    """Logout + clear the Zalo session and owner. / Đăng xuất + xóa phiên Zalo và owner."""
    await _safe_request(settings, "POST", "/logout")
    delete_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID")
    return ok({"disconnected": True})
