"""Log tail + SSE stream + log file listing. / Route log: tail + stream SSE + danh sách file."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from .. import systemd_ctl
from ..config import Settings, get_settings
from ..hermes_fs import list_log_files
from ..models import ok

router = APIRouter(prefix="/api/logs", tags=["logs"])

DEFAULT_SERVICE = "hermes-gateway"


@router.get("")
async def tail_logs(
    service: str = Query(DEFAULT_SERVICE),
    lines: int = Query(100, ge=1, le=5000),
    priority: str | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> Any:
    """journalctl tail for one service. / journalctl tail cho một dịch vụ."""
    entries = await systemd_ctl.journal_tail(service, lines=lines, priority=priority)
    return ok({"service": service, "lines": lines, "entries": entries})


@router.get("/stream")
async def stream_logs(service: str = Query(DEFAULT_SERVICE)) -> StreamingResponse:
    """SSE stream emitting new journal lines. / Stream SSE nhả dòng journal mới."""

    async def event_source() -> AsyncIterator[str]:
        yield f"event: ready\ndata: {json.dumps({'service': service})}\n\n"
        try:
            async for line in systemd_ctl.journal_stream(service):
                yield f"data: {json.dumps({'line': line})}\n\n"
        except Exception as exc:  # pragma: no cover - defensive / phòng thủ
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.get("/files")
async def log_files(settings: Settings = Depends(get_settings)) -> Any:
    """List files under the system log directory. / Liệt kê file trong thư mục log."""
    files = list_log_files(settings.log_dir)
    return ok({"files": files, "count": len(files)})
