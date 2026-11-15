"""Async `hermes` CLI runner with a subcommand whitelist. / Chạy CLI `hermes` bất đồng bộ + danh sách cho phép."""

from __future__ import annotations

from . import systemd_ctl
from .config import Settings
from .systemd_ctl import CommandResult

HERMES_WHITELIST: tuple[str, ...] = (
    "version",
    "status",
    "doctor",
    "config",
    "model",
    "cron",
    "gateway",
    "logs",
    "skills",
    "sessions",
    "memory",
    "tools",
    "insights",
    "auth",
)


def is_whitelisted(subcommand: str) -> bool:
    """True when the subcommand is allowed. / True khi subcommand được phép."""
    return subcommand in HERMES_WHITELIST


async def run_hermes(settings: Settings, args: list[str], timeout: float = 60.0) -> CommandResult:
    """Run `hermes <args>` without a shell. / Chạy `hermes <args>`, không qua shell."""
    argv = [settings.hermes_bin, *args]
    return await systemd_ctl.run_command(*argv, timeout=timeout)


async def run_whitelisted(settings: Settings, subcommand: str, args: list[str] | None = None) -> CommandResult:
    """Run a whitelisted hermes subcommand; ValueError otherwise. / Chạy subcommand được phép; ngược lại ValueError."""
    if not is_whitelisted(subcommand):
        raise ValueError(f"subcommand not allowed: {subcommand}")
    return await run_hermes(settings, [subcommand, *(args or [])])
