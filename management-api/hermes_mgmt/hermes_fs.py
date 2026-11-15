"""Read Hermes config.yaml (PyYAML) + log files helpers. / Đọc config.yaml của Hermes + helper file log."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .env_file import SENSITIVE_RE, mask_value


def read_config_yaml(path: Path) -> dict[str, Any]:
    """Parse Hermes config.yaml into a dict. / Đọc config.yaml của Hermes thành dict."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return {}
    data = yaml.safe_load(raw)
    return data if isinstance(data, dict) else {}


def write_config_yaml(path: Path, data: dict[str, Any]) -> None:
    """Atomically write config.yaml. / Ghi config.yaml nguyên tử."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".cfg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def mask_structure(obj: Any) -> Any:
    """Recursively mask sensitive keys in a config structure. / Che khóa nhạy cảm trong cấu trúc config."""
    if isinstance(obj, dict):
        masked: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(value, str) and SENSITIVE_RE.search(str(key)):
                masked[str(key)] = mask_value(str(key), value)
            else:
                masked[str(key)] = mask_structure(value)
        return masked
    if isinstance(obj, list):
        return [mask_structure(item) for item in obj]
    return obj


def normalize_model(provider: str, model: str) -> str:
    """Return `<provider>/<bare-model>`, stripping a duplicate prefix. / Trả về provider/model, bỏ prefix trùng."""
    prefix = f"{provider}/"
    bare = model[len(prefix):] if model.startswith(prefix) else model
    return f"{provider}/{bare}"


def set_model_config(config: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    """Set model.default + model.provider in a config dict. / Đặt model.default + model.provider."""
    section = config.get("model")
    if not isinstance(section, dict):
        section = {}
    section["default"] = normalize_model(provider, model)
    section["provider"] = provider
    config["model"] = section
    return config


def list_log_files(log_dir: Path) -> list[dict[str, Any]]:
    """List log files under a directory (one level deep). / Liệt kê file log trong thư mục."""
    entries: list[dict[str, Any]] = []
    root = Path(log_dir)
    if not root.exists():
        return entries
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        rel = item.relative_to(root)
        # Only descend one level into subdirectories. / Chỉ lún một cấp vào thư mục con.
        if len(rel.parts) > 2:
            continue
        entries.append(
            {
                "name": rel.as_posix(),
                "path": str(item),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )
    return entries


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def valid_env_key(key: str) -> bool:
    """True for a valid env var name. / True nếu là tên biến env hợp lệ."""
    return bool(_ENV_KEY_RE.fullmatch(key))
