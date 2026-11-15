"""Environment variable routes over /opt/hermes/.env. / Route biến môi trường trên /opt/hermes/.env."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..env_file import delete_env_value, mask_env_map, read_env_map, set_env_value
from ..hermes_fs import valid_env_key
from ..models import EnvPutRequest, fail, ok

router = APIRouter(prefix="/api/env", tags=["env"])


@router.get("")
async def list_env(settings: Settings = Depends(get_settings)) -> Any:
    """All env keys with sensitive values masked. / Mọi key env, giá trị nhạy cảm đã che."""
    values = read_env_map(settings.mgmt_env_file)
    return ok({"vars": mask_env_map(values), "count": len(values)})


@router.put("/{key}")
async def put_env(
    key: str,
    body: EnvPutRequest,
    settings: Settings = Depends(get_settings),
) -> Any:
    """Upsert one env var atomically. / Ghi đè một biến env (nguyên tử)."""
    if not valid_env_key(key):
        raise HTTPException(status_code=422, detail=f"invalid env key: {key}")
    set_env_value(settings.mgmt_env_file, key, body.value)
    return ok({"key": key, "saved": True})


@router.delete("/{key}")
async def delete_env(key: str, settings: Settings = Depends(get_settings)) -> Any:
    """Remove one env var (404 when absent). / Xóa một biến env (404 nếu không có)."""
    if not valid_env_key(key):
        raise HTTPException(status_code=422, detail=f"invalid env key: {key}")
    removed = delete_env_value(settings.mgmt_env_file, key)
    if not removed:
        return fail(f"env key not found: {key}", 404)
    return ok({"key": key, "deleted": True})
