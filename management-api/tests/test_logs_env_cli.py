"""Logs + env + CLI passthrough tests. / Test log + env + CLI."""

from __future__ import annotations

import json

from conftest import assert_fail, assert_ok
from hermes_mgmt import systemd_ctl
from hermes_mgmt.env_file import get_env_value


def test_logs_requires_auth(client):
    assert_fail(client.get("/api/logs"), 401)


def test_logs_tail(client, auth_headers, runner):
    runner.set_result("journalctl", stdout="line one\nline two\n")
    payload = assert_ok(client.get("/api/logs?service=hermes-gateway&lines=20", headers=auth_headers))
    assert payload["data"] == {
        "service": "hermes-gateway",
        "lines": 20,
        "entries": ["line one", "line two"],
    }
    assert runner.called_with("journalctl", "-u", "hermes-gateway", "-n", "20")


def test_logs_priority_flag(client, auth_headers, runner):
    assert_ok(client.get("/api/logs?priority=err", headers=auth_headers))
    assert runner.called_with("journalctl", "-u", "hermes-gateway", "-n", "100")


def test_logs_files(client, auth_headers, settings):
    (settings.log_dir / "app.log").write_text("x" * 10, encoding="utf-8")
    (settings.log_dir / "caddy" / "access.log").write_text("y" * 5, encoding="utf-8")
    payload = assert_ok(client.get("/api/logs/files", headers=auth_headers))
    names = {item["name"] for item in payload["data"]["files"]}
    assert names == {"app.log", "caddy/access.log"}
    assert payload["data"]["count"] == 2
    sizes = {item["name"]: item["size"] for item in payload["data"]["files"]}
    assert sizes["app.log"] == 10


def test_logs_stream_sse(client, auth_headers, monkeypatch):
    async def fake_stream(unit: str):
        yield "hello world"
        yield "second line"

    monkeypatch.setattr(systemd_ctl, "journal_stream", fake_stream)
    response = client.get("/api/logs/stream", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: ready" in body
    assert f"data: {json.dumps({'line': 'hello world'})}" in body
    assert f"data: {json.dumps({'line': 'second line'})}" in body


def test_env_list_masks_secrets(client, auth_headers):
    payload = assert_ok(client.get("/api/env", headers=auth_headers))
    variables = payload["data"]["vars"]
    assert variables["DOMAIN"] == "test.example.com"
    assert variables["HERMES_MGMT_API_KEY"] == "sk-****-key"
    assert variables["OPENAI_API_KEY"] == "sk-****7890"
    assert "test-api-key" not in str(payload)
    assert "sk-test-1234567890" not in str(payload)


def test_env_put_and_delete_roundtrip(client, auth_headers, settings):
    created = assert_ok(client.put("/api/env/HERMES_SMOKE_TEST", headers=auth_headers, json={"value": "smoke-ok"}))
    assert created["data"] == {"key": "HERMES_SMOKE_TEST", "saved": True}
    assert get_env_value(settings.mgmt_env_file, "HERMES_SMOKE_TEST") == "smoke-ok"
    deleted = assert_ok(client.delete("/api/env/HERMES_SMOKE_TEST", headers=auth_headers))
    assert deleted["data"] == {"key": "HERMES_SMOKE_TEST", "deleted": True}
    assert get_env_value(settings.mgmt_env_file, "HERMES_SMOKE_TEST") is None


def test_env_put_invalid_key_422(client, auth_headers):
    response = client.put("/api/env/BAD-KEY", headers=auth_headers, json={"value": "x"})
    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_env_put_empty_body_422(client, auth_headers):
    response = client.put("/api/env/GOOD_KEY", headers=auth_headers, json={})
    assert response.status_code == 422


def test_env_delete_missing_404(client, auth_headers):
    assert_fail(client.delete("/api/env/NOT_THERE", headers=auth_headers), 404)


def test_cli_whitelisted(client, auth_headers, runner):
    runner.set_result("hermes", "version", stdout="Hermes v1\n")
    payload = assert_ok(client.post("/api/cli", headers=auth_headers, json={"subcommand": "version", "args": []}))
    assert payload["data"] == {"exit_code": 0, "stdout": "Hermes v1\n", "stderr": ""}
    assert runner.called_with("hermes", "version")


def test_cli_passes_extra_args(client, auth_headers, runner):
    assert_ok(client.post("/api/cli", headers=auth_headers, json={"subcommand": "config", "args": ["get", "model"]}))
    assert runner.called_with("hermes", "config", "get", "model")


def test_cli_non_whitelisted_400(client, auth_headers, runner):
    assert_fail(client.post("/api/cli", headers=auth_headers, json={"subcommand": "secrets", "args": []}), 400)
    assert not runner.called_with("hermes", "secrets")


def test_cli_empty_body_422(client, auth_headers):
    response = client.post("/api/cli", headers=auth_headers, json={})
    assert response.status_code == 422
