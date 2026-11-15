"""Agent roles + rule-group policy routes. / Route vai trò agent + nhóm quy tắc."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException

from .. import systemd_ctl
from ..config import Settings, get_settings
from ..hermes_fs import read_config_yaml, write_config_yaml
from ..models import RoleCreateRequest, fail, ok

router = APIRouter(prefix="/api", tags=["roles"])

RULE_GROUP_IDS: tuple[str, ...] = (
    "a-identity",
    "b-account-safety",
    "c-anti-spam-content",
    "d-security-privacy",
    "e-marketing-sales",
    "f-conversation-quality",
    "g-tools-actions",
    "h-operations-escalation",
)


def _rules_dir(settings: Settings) -> Path:
    return Path(settings.roles_config_dir) / "rules"


def _preset_roles_dir(settings: Settings) -> Path:
    return Path(settings.roles_config_dir) / "roles"


def _title_of(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def load_rule_group(settings: Settings, group_id: str) -> dict[str, Any] | None:
    """Load one rule-group markdown. / Đọc markdown một nhóm quy tắc."""
    path = _rules_dir(settings) / f"{group_id}.md"
    try:
        body = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None
    return {"id": group_id, "title": _title_of(body, group_id), "body": body}


def load_rule_groups(settings: Settings) -> list[dict[str, Any]]:
    """Load every rule group (sorted by id). / Đọc mọi nhóm quy tắc."""
    groups: list[dict[str, Any]] = []
    root = _rules_dir(settings)
    if not root.exists():
        return groups
    for path in sorted(root.glob("*.md")):
        group = load_rule_group(settings, path.stem)
        if group:
            groups.append(group)
    return groups


def _read_role_yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _role_view(data: dict[str, Any], source: str) -> dict[str, Any]:
    """Normalize a role yaml into the API shape. / Chuẩn hóa role yaml về dạng API."""
    persona = str(data.get("persona_vi") or data.get("persona") or "")
    return {
        "id": str(data.get("id", "")),
        "label": str(data.get("label_vi") or data.get("label") or data.get("id", "")),
        "label_vi": data.get("label_vi") or data.get("label") or "",
        "label_en": data.get("label_en") or "",
        "description": str(data.get("description_vi") or data.get("description") or ""),
        "emoji": str(data.get("emoji") or ""),
        "tone": str(data.get("tone") or ""),
        "persona": persona,
        "persona_en": str(data.get("persona_en") or persona),
        "rules": [str(item) for item in (data.get("rules") or [])],
        "source": source,
    }


def load_roles(settings: Settings) -> list[dict[str, Any]]:
    """Preset (read-only) + custom roles. / Role preset (chỉ đọc) + role tùy chỉnh."""
    roles: list[dict[str, Any]] = []
    for path in sorted(_preset_roles_dir(settings).glob("*.yaml")):
        data = _read_role_yaml(path)
        if data:
            data.setdefault("id", path.stem)
            roles.append(_role_view(data, "preset"))
    for path in sorted(Path(settings.roles_dir_custom).glob("*.yaml")):
        data = _read_role_yaml(path)
        if data:
            data.setdefault("id", path.stem)
            roles.append(_role_view(data, "custom"))
    return roles


def find_role(settings: Settings, role_id: str) -> dict[str, Any] | None:
    for role in load_roles(settings):
        if role["id"] == role_id:
            return role
    return None


def active_role(settings: Settings) -> dict[str, Any] | None:
    try:
        data = json.loads(settings.active_role_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@router.get("/rules")
async def list_rules(settings: Settings = Depends(get_settings)) -> Any:
    """List all rule groups with full markdown bodies. / Liệt kê nhóm quy tắc kèm nội dung."""
    groups = load_rule_groups(settings)
    return ok({"groups": groups, "count": len(groups)})


@router.get("/rules/{group_id}")
async def get_rule(group_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """One rule group's markdown (404 unknown). / Markdown một nhóm quy tắc (404 nếu không có)."""
    group = load_rule_group(settings, group_id)
    if group is None:
        return fail(f"rule group not found: {group_id}", 404)
    return ok(group)


@router.get("/roles")
async def list_roles(settings: Settings = Depends(get_settings)) -> Any:
    """List preset + custom roles and the active role id. / Liệt kê role + role đang bật."""
    roles = load_roles(settings)
    current = active_role(settings)
    return ok({"roles": roles, "active_role_id": (current or {}).get("id")})


@router.get("/roles/active")
async def get_active_role(settings: Settings = Depends(get_settings)) -> Any:
    """Currently applied role (404 when none). / Role đang áp dụng (404 nếu chưa có)."""
    current = active_role(settings)
    if current is None:
        return fail("no active role", 404)
    return ok({"id": current.get("id"), "rules": current.get("rules", []), "applied_at": current.get("applied_at")})


@router.get("/roles/{role_id}")
async def get_role(role_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Role detail (persona, tone, rules, source). / Chi tiết role."""
    role = find_role(settings, role_id)
    if role is None:
        return fail(f"role not found: {role_id}", 404)
    return ok(role)


@router.post("/roles")
async def upsert_role(body: RoleCreateRequest, settings: Settings = Depends(get_settings)) -> Any:
    """Create/update a custom role (unknown rule ids dropped, presets protected). / Tạo/sửa role tùy chỉnh."""
    preset_ids = {path.stem for path in _preset_roles_dir(settings).glob("*.yaml")}
    if body.id in preset_ids:
        return fail(f"cannot shadow a preset role: {body.id}", 409)
    known_rules = set(RULE_GROUP_IDS) | {g["id"] for g in load_rule_groups(settings)}
    rules = [rule for rule in body.rules if rule in known_rules]
    data = {
        "id": body.id,
        "label_vi": body.label,
        "label_en": body.label,
        "description_vi": body.description,
        "description_en": body.description,
        "emoji": body.emoji,
        "tone": body.tone,
        "persona_vi": body.persona,
        "persona_en": body.persona,
        "rules": rules,
    }
    target = Path(settings.roles_dir_custom) / f"{body.id}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ok(_role_view(data, "custom"))


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Delete a custom role; presets are read-only (403). / Xóa role tùy chỉnh; preset bị cấm (403)."""
    preset_ids = {path.stem for path in _preset_roles_dir(settings).glob("*.yaml")}
    if role_id in preset_ids:
        return fail("preset roles cannot be deleted", 403)
    target = Path(settings.roles_dir_custom) / f"{role_id}.yaml"
    if not target.exists():
        return fail(f"role not found: {role_id}", 404)
    target.unlink()
    return ok({"id": role_id, "deleted": True})


@router.post("/roles/{role_id}/apply")
async def apply_role(role_id: str, settings: Settings = Depends(get_settings)) -> Any:
    """Assemble persona + rules -> persona.md -> restart gateway. / Lắp persona + quy tắc -> persona.md -> khởi động lại."""
    role = find_role(settings, role_id)
    if role is None:
        return fail(f"role not found: {role_id}", 404)
    parts = [role["persona"].strip(), ""]
    for group_id in role["rules"]:
        group = load_rule_group(settings, group_id)
        if group:
            parts.append(group["body"].strip())
            parts.append("")
    persona_text = "\n".join(parts).strip() + "\n"
    settings.persona_file.parent.mkdir(parents=True, exist_ok=True)
    settings.persona_file.write_text(persona_text, encoding="utf-8")
    record = {
        "id": role["id"],
        "rules": role["rules"],
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    settings.active_role_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    await systemd_ctl.systemctl("restart", "hermes-gateway")
    return ok({"id": role["id"], "rules": role["rules"], "persona_preview": persona_text, "applied_at": record["applied_at"]})
