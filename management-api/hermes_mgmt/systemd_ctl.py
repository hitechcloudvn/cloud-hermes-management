"""Async subprocess wrappers for systemctl + journalctl. / Bọc subprocess bất đồng bộ cho systemctl + journalctl."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

HERMES_TARGET = "hermes.target"
UNIT_GATEWAY = "hermes-gateway.service"
UNIT_DASHBOARD = "hermes-dashboard.service"
UNIT_MGMT = "hermes-mgmt.service"
UNIT_CADDY = "caddy.service"
CORE_UNITS = (UNIT_GATEWAY, UNIT_DASHBOARD, UNIT_MGMT, UNIT_CADDY)


@dataclass
class CommandResult:
    """Outcome of one subprocess run. / Kết quả của một lần chạy subprocess."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


async def _spawn(*argv: str, timeout: float = 60.0, cwd: str | None = None) -> CommandResult:
    """Lowest-level exec seam (tests patch this to forbid real subprocesses). / Chạy tiến trình (test vá để cấm chạy thật)."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return CommandResult(exit_code=124, stdout="", stderr=f"timeout after {timeout}s")
    return CommandResult(
        exit_code=process.returncode or 0,
        stdout=stdout_b.decode("utf-8", errors="replace"),
        stderr=stderr_b.decode("utf-8", errors="replace"),
    )


async def run_command(*argv: str, timeout: float = 60.0, cwd: str | None = None) -> CommandResult:
    """Run one command without a shell. / Chạy một lệnh, không qua shell."""
    return await _spawn(*argv, timeout=timeout, cwd=cwd)


async def systemctl(*args: str, timeout: float = 60.0) -> CommandResult:
    """Run systemctl with args. / Chạy systemctl với tham số."""
    return await run_command("systemctl", *args, timeout=timeout)


async def is_active(unit: str) -> bool:
    """True when systemctl reports the unit active. / True khi systemctl báo unit đang chạy."""
    result = await systemctl("is-active", unit)
    return result.exit_code == 0


async def unit_state(unit: str) -> str:
    """Return systemctl is-active output ('active', 'inactive', ...). / Trả về trạng thái unit."""
    result = await systemctl("is-active", unit)
    return (result.stdout or result.stderr).strip() or ("active" if result.exit_code == 0 else "unknown")


async def journal_tail(unit: str, lines: int = 100, priority: str | None = None) -> list[str]:
    """Return the last journal lines for a unit. / Trả về các dòng journal cuối của unit."""
    argv = ["journalctl", "-u", unit, "-n", str(max(1, lines)), "--no-pager", "-o", "cat"]
    if priority:
        argv += ["-p", priority]
    result = await run_command(*argv)
    text = result.stdout or result.stderr
    return [line for line in text.splitlines()]


async def journal_stream(unit: str) -> AsyncIterator[str]:
    """Yield new journal lines as they arrive. / Nhả dòng journal mới khi có."""
    process = await asyncio.create_subprocess_exec(
        "journalctl",
        "-u",
        unit,
        "-f",
        "-n",
        "0",
        "--no-pager",
        "-o",
        "cat",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdout is not None
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace").rstrip("\n")
    finally:
        process.kill()
