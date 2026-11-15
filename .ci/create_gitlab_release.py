#!/usr/bin/env python3
"""Tao GitLab Release qua Releases API / Create the GitLab Release via the Releases API.

Vi sao khong dung keyword `release:` cua GitLab CI / Why not the `release:` keyword:

1. gitlab-runner 19.6+ (SaaS) sinh buoc "step_release" dang
   `if command -v glab; then glab ...; else release-cli ...` — ca hai binary
   deu KHONG co trong image chay job (vi du python:3.11-slim) => exit 127.
   / gitlab-runner 19.6+ (SaaS) generates a release step of the form
   `if command -v glab; then glab ...; else release-cli ...` — neither binary
   exists in the job image (e.g. python:3.11-slim) => exit 127.

2. Buoc do embed mo ta markdown vao script shell — cac backtick trong mo ta
   (vi du `install.sh`) bi bash hieu la command substitution va duoc THUC THI,
   ke ca dong `curl ... | bash` trong code block.
   / That step embeds the markdown description into shell script code —
   backticks in the description (e.g. `install.sh`) are executed by bash as
   command substitution, including the `curl ... | bash` code-block line.

Goi Releases API truc tiep bang CI_JOB_TOKEN (header JOB-TOKEN) la duong dan
on dinh, khong phu thuoc release-cli/glab hoac ki tu dac biet trong mo ta.
/ Calling the Releases API directly with CI_JOB_TOKEN (JOB-TOKEN header) is
stable, independent of release-cli/glab and of special characters in the notes.

Chi dung stdlib — khong can package nao them / stdlib only — no extra packages.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Mo ta release song ngu / bilingual release notes
NOTES = """\
## Tiếng Việt

Bản phát hành đầu tiên của **cloud-hermes-management** — bộ công cụ triển khai Hermes Agent lên VPS bare-metal (Ubuntu 24.04):

- **Management API** (FastAPI) với 73 endpoint quản trị
- **RAG MCP** — dịch vụ truy xuất tri thức cục bộ
- **Trình cài đặt bare-metal** (`install.sh` / `bootstrap.sh`)
- Wheel/sdist do CI xây dựng, kèm checksum `SHA256SUMS.txt`

Cài đặt bằng lệnh sau từ tổ chức `hitechcloudvn`:

```bash
curl -fsSL https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main/install.sh | bash
```

## English

First release of **cloud-hermes-management** — bare-metal deployment wrapper for Hermes Agent (Ubuntu 24.04 VPS):

- **Management API** (FastAPI) with 73 endpoints
- **RAG MCP** — local knowledge retrieval service
- **Bare-metal installer** (`install.sh` / `bootstrap.sh`)
- CI/CD-built wheels/sdists with `SHA256SUMS.txt` checksums

Install with the following command from the `hitechcloudvn` org:

```bash
curl -fsSL https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main/install.sh | bash
```
"""

RESPONSE_FILE = Path("release-response.json")


def build_payload(tag: str, project_url: str, job_id: str, dist: Path) -> dict:
    """Payload cho POST /projects/:id/releases / payload for the Releases API."""
    if not dist.is_dir():
        sys.exit(f"ERROR: {dist}/ not found — build job artifacts missing?")

    links = []
    for path in sorted(dist.iterdir()):
        if not path.is_file():
            continue
        link_type = "other" if path.name == "SHA256SUMS.txt" else "package"
        links.append(
            {
                "name": path.name,
                "url": f"{project_url}/-/jobs/{job_id}/artifacts/file/dist/{path.name}",
                "link_type": link_type,
            }
        )
    if not links:
        sys.exit(f"ERROR: {dist}/ is empty — nothing to attach to the release")

    return {
        "name": tag,
        "tag_name": tag,
        "description": NOTES,
        "assets": {"links": links},
    }


def api_call(method: str, url: str, token: str, payload: dict | None = None):
    """Moi goi API luon tra ve (status, body) — khong nem loi / never raises."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "JOB-TOKEN": token,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return e.code, parsed


def save_response(status: int, body: object) -> None:
    RESPONSE_FILE.write_text(
        json.dumps({"http_status": status, "body": body}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    if "--print" in sys.argv:
        # Che do kiem tra payload cuc bo / local payload inspection mode
        payload = build_payload(
            os.environ.get("CI_COMMIT_TAG", "v0.0.0-print"),
            os.environ.get("CI_PROJECT_URL", "https://gitlab.com/example/project"),
            os.environ.get("CI_JOB_ID", "0"),
            Path(os.environ.get("DIST_DIR", "dist")),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    api_v4 = os.environ["CI_API_V4_URL"]
    project_id = os.environ["CI_PROJECT_ID"]
    tag = os.environ["CI_COMMIT_TAG"]
    job_id = os.environ["CI_JOB_ID"]
    project_url = os.environ["CI_PROJECT_URL"]
    token = os.environ["CI_JOB_TOKEN"]

    payload = build_payload(tag, project_url, job_id, Path("dist"))

    print(f"Creating GitLab release for tag {tag}")
    for link in payload["assets"]["links"]:
        print(f"  asset: {link['name']} ({link['link_type']})")

    url = f"{api_v4}/projects/{project_id}/releases"
    status, body = api_call("POST", url, token, payload)

    # Release da ton tai (vi du chay lai pipeline) — cap nhat lai / already
    # exists (pipeline re-run): update in place instead of failing the job.
    if status in (409, 422):
        print(f"Release already exists (HTTP {status}) — updating via PUT")
        status, body = api_call("PUT", f"{url}/{tag}", token, payload)

    save_response(status, body)
    if 200 <= status < 300:
        print(f"Release created/updated: {body.get('_links', {}).get('self', url)}")
        return 0

    print(f"ERROR: release API returned HTTP {status}", file=sys.stderr)
    print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    # Dam bao stdout/stderr la UTF-8 ke ca khi locale la POSIX/ASCII (Docker)
    # / force UTF-8 stdout/stderr even under POSIX/ASCII locales (Docker)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    sys.exit(main())
