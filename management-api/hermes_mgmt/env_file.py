"""Atomic .env read/write (temp + os.replace) plus key masking. / Đọc ghi .env nguyên tử + che khóa."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

SENSITIVE_RE = re.compile(r"(_KEY|_TOKEN|_SECRET|_PASSWORD|_HASH)$", re.IGNORECASE)


def mask_value(key: str, value: str) -> str:
    """Render a sensitive value as sk-****<last4>. / Hiển thị giá trị nhạy cảm dạng sk-****<4 ký tự cuối>."""
    if not value:
        return ""
    return f"sk-****{value[-4:]}"


def is_sensitive(key: str) -> bool:
    return bool(SENSITIVE_RE.search(key))


def read_env_map(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from an env file (comments ignored). / Đọc cặp KEY=VALUE từ file env."""
    result: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return result
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def get_env_value(path: Path, key: str) -> str | None:
    """Return one env value or None. / Trả về một giá trị env hoặc None."""
    return read_env_map(path).get(key)


def _write_atomic(path: Path, content: str) -> None:
    """Write file atomically via temp file + os.replace. / Ghi file nguyên tử qua temp + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".env-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_lines(path: Path) -> list[str]:
    try:
        return Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, FileNotFoundError):
        return []


def set_env_value(path: Path, key: str, value: str) -> None:
    """Upsert one KEY=VALUE line, preserving comments. / Ghi đè/thêm một dòng KEY=VALUE, giữ nguyên comment."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        raise ValueError(f"invalid env key: {key!r}")
    lines = _read_lines(path)
    prefix = f"{key}="
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith("#"):
            continue
        if line.split("=", 1)[0].strip() == key:
            lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{key}={value}")
    text = "\n".join(lines) + "\n"
    _write_atomic(Path(path), text)


def delete_env_value(path: Path, key: str) -> bool:
    """Remove a KEY=VALUE line; True if it existed. / Xóa dòng KEY=VALUE; True nếu có tồn tại."""
    lines = _read_lines(path)
    kept: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith("#"):
            kept.append(line)
            continue
        if line.split("=", 1)[0].strip() == key:
            found = True
            continue
        kept.append(line)
    if found:
        _write_atomic(Path(path), "\n".join(kept) + ("\n" if kept else ""))
    return found


def mask_env_map(values: dict[str, str]) -> dict[str, str]:
    """Mask sensitive values in a mapping. / Che giá trị nhạy cảm trong ánh xạ."""
    return {key: (mask_value(key, value) if is_sensitive(key) else value) for key, value in values.items()}
