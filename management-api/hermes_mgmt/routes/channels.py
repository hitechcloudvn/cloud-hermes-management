"""Messaging channel routes (config.yaml upsert). / Route kênh nhắn tin (ghi vào config.yaml)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..hermes_fs import mask_structure, read_config_yaml, write_config_yaml
from ..models import ChannelPutRequest, fail, ok

router = APIRouter(prefix="/api", tags=["channels"])

CHANNEL_IDS: tuple[str, ...] = ("telegram", "discord", "slack", "signal", "whatsapp", "email")

# Fallback required fields when a channel template is missing. / Trường bắt buộc dự phòng khi thiếu template.
FALLBACK_REQUIRED: dict[str, tuple[str, ...]] = {
    "telegram": ("token", "chat_id"),
    "discord": ("bot_token",),
    "slack": ("bot_token", "app_token"),
    "signal": ("account",),
    "whatsapp": ("token", "phone_id"),
    "email": ("smtp_host", "address"),
}


def _channel_template(settings: Settings, channel: str) -> dict[str, Any] | None:
    path = Path(settings.templates_dir) / "channels" / f"{channel}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def required_fields(settings: Settings, channel: str) -> tuple[str, ...]:
    """Required fields for one channel (template first). / Trường bắt buộc của một kênh."""
    template = _channel_template(settings, channel)
    if template and isinstance(template.get("required_fields"), list):
        return tuple(str(item) for item in template["required_fields"])
    return FALLBACK_REQUIRED.get(channel, ())


def _config_path(settings: Settings) -> Path:
    return settings.hermes_home / "config.yaml"


@router.get("/channels")
async def list_channels(settings: Settings = Depends(get_settings)) -> Any:
    """List configured + available messaging channels. / Liệt kê kênh đã cấu hình + khả dụng."""
    config = read_config_yaml(_config_path(settings))
    configured = config.get("channels")
    configured = configured if isinstance(configured, dict) else {}
    items: list[dict[str, Any]] = []
    for channel in CHANNEL_IDS:
        template = _channel_template(settings, channel) or {}
        entry: dict[str, Any] = {
            "id": channel,
            "label_vi": template.get("label_vi", channel),
            "label_en": template.get("label_en", channel),
            "required_fields": list(required_fields(settings, channel)),
            "configured": channel in configured,
        }
        if channel in configured:
            entry["config"] = mask_structure(configured[channel])
        items.append(entry)
    return ok({"channels": items})


@router.put("/channels/{channel}")
async def upsert_channel(
    channel: str,
    body: ChannelPutRequest,
    settings: Settings = Depends(get_settings),
) -> Any:
    """Upsert channel config in config.yaml. / Ghi đè cấu hình kênh vào config.yaml."""
    if channel not in CHANNEL_IDS:
        return fail(f"unknown channel: {channel}", 404)
    fields = dict(body.model_extra or {})
    missing = [name for name in required_fields(settings, channel) if not fields.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing required fields: {', '.join(missing)}")
    config = read_config_yaml(_config_path(settings))
    channels = config.get("channels")
    if not isinstance(channels, dict):
        channels = {}
    channels[channel] = fields
    config["channels"] = channels
    write_config_yaml(_config_path(settings), config)
    return ok({"id": channel, "config": fields})


@router.delete("/channels/{channel}")
async def delete_channel(channel: str, settings: Settings = Depends(get_settings)) -> Any:
    """Remove a configured channel (404 when not configured). / Xóa kênh đã cấu hình (404 nếu chưa có)."""
    config = read_config_yaml(_config_path(settings))
    channels = config.get("channels")
    if not isinstance(channels, dict) or channel not in channels:
        return fail(f"channel not configured: {channel}", 404)
    del channels[channel]
    config["channels"] = channels
    write_config_yaml(_config_path(settings), config)
    return ok({"id": channel, "deleted": True})
