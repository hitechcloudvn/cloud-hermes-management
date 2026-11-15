"""OpenAI Codex device-code OAuth routes. / Route OAuth device-code của OpenAI Codex."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from .. import cli_runner, systemd_ctl
from ..config import Settings, get_settings
from ..hermes_fs import read_config_yaml, write_config_yaml
from ..models import CodexDisableRequest, CodexImportRequest, fail, ok

router = APIRouter(prefix="/api/codex/auth", tags=["codex"])

CODEX_PROVIDER = "openai-codex"

# In-memory device-flow state. / Trạng thái device-flow trong bộ nhớ.
_state: dict[str, Any] = {
    "status": "disconnected",  # disconnected | pending | connected
    "url": None,
    "code": None,
    "model_set": False,
}

_URL_RE = re.compile(r"https?://\S+")
_CODE_RE = re.compile(r"\b([A-Z0-9]{4,6}-[A-Z0-9]{4,8})\b")


def reset_state() -> None:
    """Reset the in-memory auth state (tests). / Đặt lại trạng thái auth (cho tests)."""
    _state.update({"status": "disconnected", "url": None, "code": None, "model_set": False})


def _auth_file(settings: Settings) -> Path:
    return settings.hermes_home / "auth.json"


def _read_auth(settings: Settings) -> dict[str, Any]:
    try:
        data = json.loads(_auth_file(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_auth(settings: Settings, data: dict[str, Any]) -> None:
    path = _auth_file(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _has_codex_entry(data: dict[str, Any]) -> bool:
    return bool(data.get(CODEX_PROVIDER) or data.get("codex"))


def _apply_model(settings: Settings, provider: str | None) -> None:
    """Point config.yaml model.provider and restart the gateway. / Đặt model.provider và khởi động lại gateway."""
    config_path = settings.hermes_home / "config.yaml"
    config = read_config_yaml(config_path)
    model = config.get("model")
    if not isinstance(model, dict):
        model = {}
    if provider:
        model["provider"] = provider
    else:
        model.pop("provider", None)
    config["model"] = model
    write_config_yaml(config_path, config)


async def _mark_connected_if_ready(settings: Settings) -> bool:
    """Detect a completed login in auth.json; switch model on first success. / Phát hiện đăng nhập xong trong auth.json."""
    if _state["model_set"] and _state["status"] == "connected":
        return True
    if _has_codex_entry(_read_auth(settings)):
        if not _state["model_set"]:
            _apply_model(settings, "codex")
            await systemd_ctl.systemctl("restart", "hermes-gateway")
            _state["model_set"] = True
        _state["status"] = "connected"
        return True
    return False


@router.post("/start")
async def codex_start(settings: Settings = Depends(get_settings)) -> Any:
    """Start device-code login; returns url + code to show the user. / Bắt đầu đăng nhập device-code; trả về url + code."""
    if await _mark_connected_if_ready(settings):
        return ok({"status": "connected", "model_set": True})
    result = await cli_runner.run_hermes(settings, ["auth", "add", CODEX_PROVIDER, "--headless"], timeout=30)
    text = f"{result.stdout}\n{result.stderr}"
    url_match = _URL_RE.search(text)
    code_match = _CODE_RE.search(text)
    url = url_match.group(0) if url_match else None
    code = code_match.group(1) if code_match else None
    _state.update({"status": "pending", "url": url, "code": code})
    return ok({"status": "pending", "url": url, "code": code})


@router.get("/status")
async def codex_status(settings: Settings = Depends(get_settings)) -> Any:
    """disconnected / pending / connected; switches model on first connect. / Trạng thái đăng nhập Codex."""
    if await _mark_connected_if_ready(settings):
        return ok({"status": "connected", "model_set": True})
    if _state["status"] == "pending":
        return ok({"status": "pending", "url": _state["url"], "code": _state["code"]})
    return ok({"status": "disconnected"})


@router.post("/import")
async def codex_import(body: CodexImportRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Import an auth.json produced by Codex CLI (fallback flow). / Nhập auth.json từ Codex CLI."""
    raw = body.auth_json
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            return fail("auth_json is not valid JSON", 400)
    else:
        data = dict(raw)
    if not isinstance(data, dict) or not _has_codex_entry(data):
        return fail("auth_json has no openai-codex entry", 400)
    _write_auth(settings, data)
    _apply_model(settings, "codex")
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    _state.update({"status": "connected", "model_set": True})
    return ok({"imported": True, "status": "connected", "model_set": True})


@router.post("/disable")
async def codex_disable(body: CodexDisableRequest | None = None, settings: Settings = Depends(get_settings)) -> Any:
    """Disconnect Codex and repoint the model provider. / Ngắt Codex và đổi provider mô hình."""
    to_provider = body.to_provider if body else None
    await cli_runner.run_hermes(settings, ["auth", "remove", CODEX_PROVIDER], timeout=30)
    data = _read_auth(settings)
    data.pop(CODEX_PROVIDER, None)
    data.pop("codex", None)
    if data.get("active_provider") in (CODEX_PROVIDER, "codex"):
        data.pop("active_provider", None)
    _write_auth(settings, data)
    _apply_model(settings, to_provider)
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    reset_state()
    return ok({"disabled": True, "model_provider": to_provider})
