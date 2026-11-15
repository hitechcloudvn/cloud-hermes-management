"""Hermes CLI passthrough (whitelisted subcommands). / Route chạy CLI Hermes (subcommand được phép)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from .. import cli_runner
from ..config import Settings, get_settings
from ..models import CliRequest, fail, ok

router = APIRouter(prefix="/api/cli", tags=["cli"])


@router.post("")
async def run_cli(body: CliRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Run `hermes <subcommand> <args>` when whitelisted. / Chạy `hermes <subcommand>` nếu được phép."""
    if not cli_runner.is_whitelisted(body.subcommand):
        return fail(f"subcommand not allowed: {body.subcommand}", 400)
    result = await cli_runner.run_hermes(settings, [body.subcommand, *body.args])
    return ok({"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr})
