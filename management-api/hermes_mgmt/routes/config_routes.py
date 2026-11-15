"""Config + provider template + API-key routes. / Route cấu hình + template nhà cung cấp + API key."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query

from ..config import Settings, get_settings
from ..env_file import delete_env_value, get_env_value, set_env_value
from ..hermes_fs import mask_structure, normalize_model, read_config_yaml, set_model_config, write_config_yaml
from ..models import ApiKeyRequest, ProviderSetRequest, TestKeyRequest, fail, ok

router = APIRouter(prefix="/api", tags=["config"])

PROVIDER_IDS: tuple[str, ...] = (
    "anthropic",
    "openai",
    "google",
    "xai",
    "deepseek",
    "groq",
    "mistral",
    "together",
    "nous-portal",
    "openrouter",
    "huggingface",
    "kimi",
    "mimo",
    "minimax",
    "zai",
)


def _config_path(settings: Settings) -> Path:
    return settings.hermes_home / "config.yaml"


def load_provider_template(settings: Settings, provider: str) -> dict[str, Any] | None:
    """Read one provider template JSON. / Đọc một template nhà cung cấp."""
    path = Path(settings.templates_dir) / f"{provider}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_provider_templates(settings: Settings) -> list[dict[str, Any]]:
    """List every provider template in the templates dir. / Liệt kê mọi template nhà cung cấp."""
    templates: list[dict[str, Any]] = []
    root = Path(settings.templates_dir)
    if not root.exists():
        return templates
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            data.setdefault("id", path.stem)
            templates.append(data)
    return templates


def _api_key_env_name(settings: Settings, provider: str) -> str:
    template = load_provider_template(settings, provider)
    if template and template.get("api_key_env"):
        return str(template["api_key_env"])
    return provider.upper().replace("-", "_") + "_API_KEY"


def _models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


@router.get("/config")
async def get_config(settings: Settings = Depends(get_settings)) -> Any:
    """Current config.yaml with API keys masked. / config.yaml hiện tại, API key đã che."""
    config = read_config_yaml(_config_path(settings))
    return ok({"config": mask_structure(config)})


@router.get("/providers")
async def providers(settings: Settings = Depends(get_settings)) -> Any:
    """List all provider templates (15 by default). / Liệt kê template nhà cung cấp (mặc định 15)."""
    items = list_provider_templates(settings)
    return ok({"providers": items, "count": len(items)})


@router.put("/config/provider")
async def set_provider(body: ProviderSetRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Set model.default + model.provider in config.yaml (idempotent prefix). / Đặt model trong config.yaml."""
    config = read_config_yaml(_config_path(settings))
    config = set_model_config(config, body.provider, body.model)
    write_config_yaml(_config_path(settings), config)
    normalized = normalize_model(body.provider, body.model)
    return ok({"provider": body.provider, "model": normalized})


@router.put("/config/api-key")
async def put_api_key(body: ApiKeyRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Write <PROVIDER>_API_KEY to .env and restart the gateway. / Ghi API key vào .env và khởi động lại gateway."""
    env_name = _api_key_env_name(settings, body.provider)
    set_env_value(settings.mgmt_env_file, env_name, body.api_key)
    from .. import systemd_ctl

    await systemd_ctl.systemctl("restart", "hermes-gateway")
    return ok({"provider": body.provider, "env_key": env_name, "saved": True})


@router.delete("/config/api-key")
async def delete_api_key(provider: str = Query(...), settings: Settings = Depends(get_settings)) -> Any:
    """Remove a provider API key from .env. / Xóa API key của nhà cung cấp khỏi .env."""
    template = load_provider_template(settings, provider)
    if template is None and provider not in PROVIDER_IDS:
        return fail(f"unknown provider: {provider}", 404)
    env_name = _api_key_env_name(settings, provider)
    removed = delete_env_value(settings.mgmt_env_file, env_name)
    return ok({"provider": provider, "env_key": env_name, "removed": removed})


@router.post("/config/test-key")
async def test_key(body: TestKeyRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Validate a key against the provider models endpoint (not saved). / Kiểm tra key với endpoint models (không lưu)."""
    template = load_provider_template(settings, body.provider)
    if template is None and body.provider not in PROVIDER_IDS:
        return fail(f"unknown provider: {body.provider}", 404)
    base_url = (template or {}).get("base_url", "https://api.openai.com")
    url = _models_url(str(base_url))
    headers = {"Authorization": f"Bearer {body.api_key}", "x-api-key": body.api_key}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return fail(f"provider request failed: {exc}", 502)
    return ok({"status_code": response.status_code, "provider": body.provider})
