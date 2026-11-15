"""Health/info/status/version/system/domain routes. / Route health/info/status/version/system/domain."""

from __future__ import annotations

import socket
from typing import Any

from fastapi import APIRouter, Depends

from .. import __version__, cli_runner, systemd_ctl
from ..config import Settings, get_settings
from ..env_file import get_env_value, read_env_map, set_env_value
from ..models import DomainRequest, fail, ok

router = APIRouter(prefix="/api", tags=["status"])


def _detect_ip() -> str:
    """Best-effort outbound IP (never 127.0.0.1 when a route exists). / IP ra ngoài tốt nhất có thể."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


@router.get("/info")
async def info(settings: Settings = Depends(get_settings)) -> Any:
    """Domain, IP, versions + one-click dashboard URL. / Domain, IP, phiên bản + URL dashboard một chạm."""
    env = read_env_map(settings.mgmt_env_file)
    domain = env.get("DOMAIN", "")
    auth_token = env.get("HERMES_AUTH_TOKEN") or None
    ip = env.get("HERMES_DROPLET_IP") or _detect_ip()
    version_result = await cli_runner.run_hermes(settings, ["version"])
    hermes_version = (version_result.stdout or version_result.stderr).strip()
    # One-click link needs both pieces; null otherwise (README: auth_token null when unset). / Link cần đủ cả hai; nếu thiếu thì null.
    dashboard_url = f"https://{domain}/?token={auth_token}" if domain and auth_token else None
    return ok(
        {
            "domain": domain,
            "ip": ip,
            "hermes_version": hermes_version,
            "mgmt_version": __version__,
            "dashboard_url": dashboard_url,
            "auth_token": auth_token,
        }
    )


@router.get("/status")
async def status(settings: Settings = Depends(get_settings)) -> Any:
    """systemd active state per Hermes service. / Trạng thái systemd từng dịch vụ Hermes."""
    services: dict[str, dict[str, Any]] = {}
    for unit in systemd_ctl.CORE_UNITS:
        active = await systemd_ctl.is_active(unit)
        state = await systemd_ctl.unit_state(unit)
        services[unit] = {"active": active, "state": state}
    return ok({"services": services})


@router.get("/version")
async def version(settings: Settings = Depends(get_settings)) -> Any:
    """Full `hermes version` output. / Toàn bộ output `hermes version`."""
    result = await cli_runner.run_hermes(settings, ["version"])
    return ok({"output": (result.stdout or result.stderr).strip(), "exit_code": result.exit_code})


@router.get("/system")
async def system_info() -> Any:
    """CPU, memory, disk, uptime, load average. / CPU, RAM, ổ đĩa, uptime, tải trung bình."""
    import os
    import time

    import psutil

    memory = psutil.virtual_memory()
    disk_root = os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(disk_root)
        disk_info: dict[str, Any] = {"total": disk.total, "used": disk.used, "percent": disk.percent}
    except OSError:
        disk_info = {"total": 0, "used": 0, "percent": 0.0}
    try:
        load_avg = list(psutil.getloadavg())
    except (OSError, NotImplementedError):
        load_avg = [0.0, 0.0, 0.0]
    uptime = time.time() - psutil.boot_time()
    return ok(
        {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "percent": memory.percent,
            },
            "disk": disk_info,
            "uptime_seconds": uptime,
            "load_avg": load_avg,
        }
    )


@router.get("/domain")
async def get_domain(settings: Settings = Depends(get_settings)) -> Any:
    """Current DOMAIN from the env file. / DOMAIN hiện tại trong file env."""
    return ok({"domain": get_env_value(settings.mgmt_env_file, "DOMAIN") or ""})


@router.put("/domain")
async def put_domain(body: DomainRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Change DOMAIN in .env and restart Caddy. / Đổi DOMAIN trong .env và khởi động lại Caddy."""
    set_env_value(settings.mgmt_env_file, "DOMAIN", body.domain)
    caddyfile = settings.install_dir / "Caddyfile"
    # Caddyfile references {$DOMAIN}, so re-rendering is a reload + restart. / Caddyfile dùng {$DOMAIN} nên chỉ cần reload + restart.
    if caddyfile.exists():
        await systemd_ctl.run_command("caddy", "reload", "--config", str(caddyfile), "--adapter", "caddyfile")
    result = await systemd_ctl.systemctl("restart", "caddy")
    if not result.ok:
        return fail(f"caddy restart failed: {result.stderr.strip()}", 500)
    return ok({"domain": body.domain, "message": "domain updated, caddy restarted"})
