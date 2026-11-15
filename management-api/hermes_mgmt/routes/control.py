"""Destructive service control routes. / Route điều khiển dịch vụ (phá hủy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import systemd_ctl
from ..config import Settings, get_settings
from ..env_file import read_env_map, set_env_value
from ..hermes_fs import read_config_yaml, write_config_yaml
from ..models import ResetRequest, fail, ok

router = APIRouter(prefix="/api", tags=["control"])

# Files mirrored by scripts/upgrade-mgmt.sh — keep both lists in sync. / Danh sách file phải khớp scripts/upgrade-mgmt.sh.
_MGMT_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "hermes_mgmt/__init__.py",
    "hermes_mgmt/main.py",
    "hermes_mgmt/config.py",
    "hermes_mgmt/auth.py",
    "hermes_mgmt/deps.py",
    "hermes_mgmt/models.py",
    "hermes_mgmt/env_file.py",
    "hermes_mgmt/systemd_ctl.py",
    "hermes_mgmt/cli_runner.py",
    "hermes_mgmt/hermes_fs.py",
    "hermes_mgmt/routes/__init__.py",
    "hermes_mgmt/routes/status.py",
    "hermes_mgmt/routes/control.py",
    "hermes_mgmt/routes/config_routes.py",
    "hermes_mgmt/routes/channels.py",
    "hermes_mgmt/routes/cron_routes.py",
    "hermes_mgmt/routes/logs.py",
    "hermes_mgmt/routes/auth_routes.py",
    "hermes_mgmt/routes/env_routes.py",
    "hermes_mgmt/routes/cli_routes.py",
    "hermes_mgmt/routes/zalo.py",
    "hermes_mgmt/routes/openviking.py",
    "hermes_mgmt/routes/codex.py",
    "hermes_mgmt/routes/roles.py",
)

_RAW_BASE = "https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main"


async def _upgrade_hermes(settings: Settings) -> None:
    """Background: git pull Hermes + reinstall + restart gateway/dashboard. / Nền: git pull + cài lại + khởi động lại."""
    await systemd_ctl.run_command("git", "-C", str(settings.hermes_src_dir), "pull", "--ff-only")
    await systemd_ctl.run_command(
        "uv",
        "pip",
        "install",
        "--python",
        str(settings.hermes_src_dir / ".venv" / "bin" / "python"),
        "-e",
        f"{settings.hermes_src_dir}[extras]",
    )
    await systemd_ctl.systemctl("restart", "hermes-gateway", "hermes-dashboard")


async def _upgrade_mgmt(settings: Settings) -> None:
    """Background: re-pull mgmt sources + reinstall + restart hermes-mgmt. / Nền: tải lại nguồn mgmt + cài lại + khởi động lại."""
    if (settings.mgmt_dir / ".git").exists():
        await systemd_ctl.run_command("git", "-C", str(settings.mgmt_dir), "pull", "--ff-only")
    else:
        for rel in _MGMT_FILES:
            target = settings.mgmt_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            await systemd_ctl.run_command("curl", "-fsSL", f"{_RAW_BASE}/management-api/{rel}", "-o", str(target))
    await systemd_ctl.run_command(
        "uv",
        "pip",
        "install",
        "--python",
        str(settings.mgmt_dir / ".venv" / "bin" / "python"),
        "-e",
        str(settings.mgmt_dir),
    )
    await systemd_ctl.systemctl("restart", "hermes-mgmt")


@router.post("/restart")
async def restart_all() -> Any:
    """Restart every Hermes service via hermes.target. / Khởi động lại toàn bộ dịch vụ qua hermes.target."""
    result = await systemd_ctl.systemctl("restart", systemd_ctl.HERMES_TARGET)
    if not result.ok:
        return fail(f"restart failed: {result.stderr.strip()}", 500)
    return ok({"message": "hermes.target restarted"})


@router.post("/stop")
async def stop_all() -> Any:
    """Stop every Hermes service. / Dừng toàn bộ dịch vụ Hermes."""
    result = await systemd_ctl.systemctl("stop", systemd_ctl.HERMES_TARGET)
    if not result.ok:
        return fail(f"stop failed: {result.stderr.strip()}", 500)
    return ok({"message": "hermes.target stopped"})


@router.post("/start")
async def start_all() -> Any:
    """Start every Hermes service. / Khởi động toàn bộ dịch vụ Hermes."""
    result = await systemd_ctl.systemctl("start", systemd_ctl.HERMES_TARGET)
    if not result.ok:
        return fail(f"start failed: {result.stderr.strip()}", 500)
    return ok({"message": "hermes.target started"})


@router.post("/rebuild")
async def rebuild(settings: Settings = Depends(get_settings)) -> Any:
    """npm install + build for the web dashboard, then restart it. / npm install + build dashboard rồi khởi động lại."""
    web_dir = settings.hermes_src_dir / "web"
    install = await systemd_ctl.run_command("npm", "install", "--no-audit", "--no-fund", cwd=str(web_dir))
    if not install.ok:
        return fail(f"npm install failed: {install.stderr.strip()}", 500)
    build = await systemd_ctl.run_command("npm", "run", "build", cwd=str(web_dir))
    if not build.ok:
        return fail(f"npm run build failed: {build.stderr.strip()}", 500)
    await systemd_ctl.systemctl("restart", "hermes-dashboard")
    return ok({"message": "web dashboard rebuilt and restarted"})


@router.post("/upgrade", status_code=202)
async def upgrade(background: BackgroundTasks, settings: Settings = Depends(get_settings)) -> Any:
    """Upgrade Hermes Agent in the background (202). / Nâng cấp Hermes Agent ở nền (202)."""
    background.add_task(_upgrade_hermes, settings)
    return ok({"message": "Hermes upgrade started in background"}, status_code=202)


@router.post("/upgrade-mgmt", status_code=202)
async def upgrade_mgmt(background: BackgroundTasks, settings: Settings = Depends(get_settings)) -> Any:
    """Self-update the management API in the background (202). / Tự cập nhật API quản trị ở nền (202)."""
    background.add_task(_upgrade_mgmt, settings)
    return ok({"message": "Management API upgrade started in background"}, status_code=202)


@router.post("/reset")
async def reset(body: ResetRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Wipe config + sessions; requires confirm='RESET'. / Xóa config + phiên; cần confirm='RESET'."""
    if body.confirm != "RESET":
        raise HTTPException(status_code=400, detail="confirm must be exactly 'RESET'")
    config_path = settings.hermes_home / "config.yaml"
    write_config_yaml(config_path, {})
    sessions_dir = settings.hermes_home / "sessions"
    if sessions_dir.exists():
        import shutil

        shutil.rmtree(sessions_dir, ignore_errors=True)
    # Keep the env file (tokens) but drop any stale in-memory state markers. / Giữ file env nhưng xóa trạng thái tạm.
    _ = read_env_map(settings.mgmt_env_file)
    return ok({"message": "config and sessions wiped"})
