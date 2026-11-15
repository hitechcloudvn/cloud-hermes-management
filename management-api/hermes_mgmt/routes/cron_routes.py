"""Cron routes wrapping `hermes cron *`. / Route cron bọc `hermes cron *`."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends

from .. import cli_runner
from ..config import Settings, get_settings
from ..models import CronCreateRequest, fail, ok

router = APIRouter(prefix="/api/cron", tags=["cron"])


def parse_jobs(stdout: str) -> list[dict[str, Any]]:
    """Parse `hermes cron list --json` output into job dicts. / Parse output thành danh sách job."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        jobs = payload.get("jobs") or payload.get("data") or []
        return [item for item in jobs if isinstance(item, dict)]
    return []


def job_id_of(job: dict[str, Any]) -> str:
    """Best-effort job identifier. / Định danh job tốt nhất có thể."""
    return str(job.get("id") or job.get("job_id") or job.get("name") or "")


async def _list_jobs(settings: Settings) -> list[dict[str, Any]]:
    result = await cli_runner.run_hermes(settings, ["cron", "list", "--json"])
    return parse_jobs(result.stdout)


@router.get("")
async def list_jobs(settings: Settings = Depends(get_settings)) -> Any:
    """List all hermes cron jobs. / Liệt kê mọi job cron."""
    jobs = await _list_jobs(settings)
    return ok({"jobs": jobs, "count": len(jobs)})


@router.get("/status")
async def cron_status(settings: Settings = Depends(get_settings)) -> Any:
    """Aggregate cron status counts. / Tổng hợp trạng thái cron."""
    jobs = await _list_jobs(settings)
    counts = {"total": len(jobs), "running": 0, "paused": 0, "failed": 0, "other": 0}
    for job in jobs:
        state = str(job.get("status") or job.get("state") or "").lower()
        if state in ("running", "active", "enabled"):
            counts["running"] += 1
        elif state in ("paused", "disabled"):
            counts["paused"] += 1
        elif state in ("failed", "error"):
            counts["failed"] += 1
        else:
            counts["other"] += 1
    return ok(counts)


@router.post("")
async def create_job(body: CronCreateRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Create a new cron job. / Tạo job cron mới."""
    args = ["cron", "create", "--name", body.name, "--schedule", body.schedule, "--prompt", body.prompt]
    if body.job_id:
        args += ["--id", body.job_id]
    if body.description:
        args += ["--description", body.description]
    result = await cli_runner.run_hermes(settings, args)
    if not result.ok:
        return fail(f"cron create failed: {result.stderr.strip() or result.stdout.strip()}", 500)
    created = parse_jobs(result.stdout)
    return ok({"created": True, "name": body.name, "schedule": body.schedule, "job": created[0] if created else None})


async def _find_job(settings: Settings, job_id: str) -> dict[str, Any] | None:
    for job in await _list_jobs(settings):
        if job_id_of(job) == job_id:
            return job
    return None


@router.post("/{job_id}/pause")
async def pause_job(job_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Pause a cron job (404 when unknown). / Tạm dừng job cron (404 nếu không có)."""
    if await _find_job(settings, job_id) is None:
        return fail(f"cron job not found: {job_id}", 404)
    result = await cli_runner.run_hermes(settings, ["cron", "pause", job_id])
    if not result.ok:
        return fail(f"cron pause failed: {result.stderr.strip()}", 500)
    return ok({"id": job_id, "paused": True})


@router.post("/{job_id}/resume")
async def resume_job(job_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Resume a paused cron job (404 when unknown). / Tiếp tục job cron (404 nếu không có)."""
    if await _find_job(settings, job_id) is None:
        return fail(f"cron job not found: {job_id}", 404)
    result = await cli_runner.run_hermes(settings, ["cron", "resume", job_id])
    if not result.ok:
        return fail(f"cron resume failed: {result.stderr.strip()}", 500)
    return ok({"id": job_id, "resumed": True})


@router.post("/{job_id}/run")
async def run_job(job_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Trigger a cron job immediately (404 when unknown). / Chạy job ngay (404 nếu không có)."""
    if await _find_job(settings, job_id) is None:
        return fail(f"cron job not found: {job_id}", 404)
    result = await cli_runner.run_hermes(settings, ["cron", "run", job_id])
    if not result.ok:
        return fail(f"cron run failed: {result.stderr.strip()}", 500)
    return ok({"id": job_id, "triggered": True})


@router.delete("/{job_id}")
async def delete_job(job_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Remove a cron job (404 when unknown). / Xóa job cron (404 nếu không có)."""
    if await _find_job(settings, job_id) is None:
        return fail(f"cron job not found: {job_id}", 404)
    result = await cli_runner.run_hermes(settings, ["cron", "remove", job_id])
    if not result.ok:
        return fail(f"cron remove failed: {result.stderr.strip()}", 500)
    return ok({"id": job_id, "deleted": True})
