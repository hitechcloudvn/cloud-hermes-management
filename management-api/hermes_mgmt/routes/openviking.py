"""OpenViking memory backend lifecycle routes. / Route vòng đời backend trí nhớ OpenViking."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from .. import systemd_ctl
from ..config import Settings, get_settings
from ..env_file import delete_env_value, get_env_value, set_env_value
from ..models import (
    OpenVikingConfigRequest,
    OpenVikingTestKeyRequest,
    OpenVikingUninstallRequest,
    fail,
    ok,
)

router = APIRouter(prefix="/api/openviking", tags=["openviking"])

DEFAULT_API_BASE = "https://api.openai.com/v1"


def _conf_path(settings: Settings) -> Path:
    return settings.openviking_home / "ov.conf"


def is_installed(settings: Settings) -> bool:
    """True when the OpenViking venv exists. / True khi venv OpenViking tồn tại."""
    return settings.openviking_dir.exists()


def read_conf(settings: Settings) -> dict[str, Any]:
    """Read ov.conf (embedding + VLM). / Đọc ov.conf."""
    try:
        data = json.loads(_conf_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def conf_ready(settings: Settings) -> bool:
    """True when ov.conf exists with a usable api_key. / True khi ov.conf có api_key dùng được."""
    conf = read_conf(settings)
    embedding = conf.get("embedding") or {}
    if isinstance(embedding, dict):
        dense = embedding.get("dense") or {}
        if isinstance(dense, dict) and dense.get("api_key"):
            return True
    return bool(conf.get("api_key"))


def write_conf(settings: Settings, body: OpenVikingConfigRequest) -> None:
    """Write ov.conf applying one api_key to embedding + VLM. / Ghi ov.conf, một api_key cho cả embedding + VLM."""
    conf = {
        "embedding": {
            "dense": {
                "api_base": body.api_base,
                "api_key": body.api_key,
                "provider": body.provider,
                "dimension": body.dimension,
                "model": body.embedding_model,
                "input": "multimodal",
            }
        },
        "vlm": {
            "api_base": body.api_base,
            "api_key": body.api_key,
            "provider": body.provider,
            "model": body.vlm_model,
        },
    }
    path = _conf_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(conf, indent=2), encoding="utf-8")


async def _health_probe(settings: Settings) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.openviking_endpoint}/stats")
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, dict) else {"raw": data}
    except (httpx.HTTPError, ValueError):
        return None
    return None


async def _install_task(settings: Settings) -> None:
    await systemd_ctl.run_command("bash", str(settings.openviking_install_script), timeout=900)


async def _upgrade_task(settings: Settings) -> None:
    await systemd_ctl.run_command(
        "bash",
        "-c",
        f"{settings.openviking_dir}/.venv/bin/pip install --upgrade openviking",
        timeout=900,
    )
    await systemd_ctl.systemctl("restart", settings.openviking_service)


async def _uninstall_task(settings: Settings, purge: bool) -> None:
    await systemd_ctl.systemctl("stop", settings.openviking_service)
    delete_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT")
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    await systemd_ctl.run_command("bash", str(settings.openviking_uninstall_script), timeout=900)
    if purge:
        shutil.rmtree(settings.openviking_home, ignore_errors=True)
        shutil.rmtree(settings.openviking_dir, ignore_errors=True)


@router.get("/status")
async def ov_status(settings: Settings = Depends(get_settings)) -> Any:
    """Lifecycle state of the OpenViking backend. / Trạng thái vòng đời backend OpenViking."""
    installed = is_installed(settings)
    configured = conf_ready(settings)
    active = await systemd_ctl.is_active(settings.openviking_service)
    wired = bool(get_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT"))
    healthy = False
    if active:
        healthy = (await _health_probe(settings)) is not None
    return ok(
        {
            "installed": installed,
            "config_ready": configured,
            "service_active": active,
            "healthy": healthy,
            "wired_into_hermes": wired,
            "endpoint": settings.openviking_endpoint,
        }
    )


@router.post("/install", status_code=202)
async def ov_install(background: BackgroundTasks, settings: Settings = Depends(get_settings)) -> Any:
    """Run the OpenViking installer in the background (202). / Chạy trình cài đặt OpenViking ở nền (202)."""
    background.add_task(_install_task, settings)
    return ok({"message": "OpenViking install started in background"}, status_code=202)


@router.get("/config")
async def ov_get_config(settings: Settings = Depends(get_settings)) -> Any:
    """Current ov.conf with api_key masked. / ov.conf hiện tại, api_key đã che."""
    conf = read_conf(settings)
    if not conf:
        return ok({"configured": False})
    embedding = conf.get("embedding") or {}
    dense = embedding.get("dense") if isinstance(embedding, dict) else {}
    dense = dense if isinstance(dense, dict) else {}
    api_key = str(dense.get("api_key") or conf.get("api_key") or "")
    masked = f"sk-****{api_key[-4:]}" if api_key else ""
    return ok(
        {
            "configured": bool(api_key),
            "api_key": masked,
            "api_base": dense.get("api_base", DEFAULT_API_BASE),
            "embedding_model": dense.get("model"),
            "vlm_model": (conf.get("vlm") or {}).get("model") if isinstance(conf.get("vlm"), dict) else None,
            "provider": dense.get("provider"),
            "dimension": dense.get("dimension"),
        }
    )


@router.post("/config")
async def ov_set_config(body: OpenVikingConfigRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Write ov.conf (embedding + VLM) with one shared api_key. / Ghi ov.conf dùng chung một api_key."""
    write_conf(settings, body)
    return ok({"configured": True, "api_base": body.api_base})


@router.post("/test-key")
async def ov_test_key(body: OpenVikingTestKeyRequest) -> Any:
    """Validate the LLM key via GET <api_base>/models (not saved). / Kiểm tra key LLM qua /models (không lưu)."""
    base = body.api_base.rstrip("/")
    url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {body.api_key}"})
    except httpx.HTTPError as exc:
        return fail(f"provider request failed: {exc}", 502)
    return ok({"status_code": response.status_code})


@router.post("/enable")
async def ov_enable(settings: Settings = Depends(get_settings)) -> Any:
    """Start the service + wire OPENVIKING_ENDPOINT + restart gateway. / Bật dịch vụ + nối endpoint + khởi động lại gateway."""
    if not is_installed(settings):
        return fail("openviking is not installed", 409)
    if not conf_ready(settings):
        return fail("openviking is not configured", 409)
    start = await systemd_ctl.systemctl("start", settings.openviking_service)
    if not start.ok:
        return fail(f"service start failed: {start.stderr.strip()}", 500)
    set_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT", settings.openviking_endpoint)
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    return ok({"enabled": True, "endpoint": settings.openviking_endpoint})


@router.post("/disable")
async def ov_disable(settings: Settings = Depends(get_settings)) -> Any:
    """Stop the service + unwire the endpoint (keeps the install). / Dừng dịch vụ + gỡ endpoint (giữ cài đặt)."""
    await systemd_ctl.systemctl("stop", settings.openviking_service)
    delete_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT")
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    return ok({"disabled": True})


@router.post("/restart")
async def ov_restart(settings: Settings = Depends(get_settings)) -> Any:
    """Restart hermes-openviking.service. / Khởi động lại hermes-openviking.service."""
    if not is_installed(settings):
        return fail("openviking is not installed", 409)
    result = await systemd_ctl.systemctl("restart", settings.openviking_service)
    if not result.ok:
        return fail(f"restart failed: {result.stderr.strip()}", 500)
    return ok({"restarted": True})


@router.post("/upgrade", status_code=202)
async def ov_upgrade(background: BackgroundTasks, settings: Settings = Depends(get_settings)) -> Any:
    """pip install --upgrade openviking in the background (202). / Nâng cấp openviking ở nền (202)."""
    if not is_installed(settings):
        return fail("openviking is not installed", 409)
    background.add_task(_upgrade_task, settings)
    return ok({"message": "OpenViking upgrade started in background"}, status_code=202)


@router.get("/stats")
async def ov_stats(settings: Settings = Depends(get_settings)) -> Any:
    """Service state + data size + best-effort live stats. / Trạng thái dịch vụ + kích thước dữ liệu + stats."""
    active = await systemd_ctl.is_active(settings.openviking_service)
    data_dir = settings.openviking_home / "data"
    size_mb = 0.0
    if data_dir.exists():
        total = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
        size_mb = round(total / (1024 * 1024), 2)
    return ok(
        {
            "service_active": active,
            "active_since": None,
            "data_dir": str(data_dir),
            "data_size_mb": size_mb,
            "server_stats": await _health_probe(settings),
        }
    )


@router.post("/uninstall", status_code=202)
async def ov_uninstall(
    background: BackgroundTasks,
    body: OpenVikingUninstallRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> Any:
    """Unwire + stop + uninstall in the background; purge deletes data. / Gỡ ở nền; purge xóa dữ liệu."""
    purge = bool(body.purge) if body else False
    background.add_task(_uninstall_task, settings, purge)
    return ok({"message": "OpenViking uninstall started in background", "purge": purge}, status_code=202)


@router.get("/logs")
async def ov_logs(lines: int = Query(100, ge=1, le=5000), settings: Settings = Depends(get_settings)) -> Any:
    """Journal tail of hermes-openviking.service. / journal tail của hermes-openviking.service."""
    entries = await systemd_ctl.journal_tail(settings.openviking_service, lines=lines)
    return ok({"service": settings.openviking_service, "lines": lines, "entries": entries})
