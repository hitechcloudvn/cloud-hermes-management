"""OpenViking lifecycle tests. / Test vòng đời OpenViking."""

from __future__ import annotations

import json

import httpx

from conftest import assert_fail, assert_ok
from hermes_mgmt.env_file import get_env_value, set_env_value

OV_CONFIG_BODY = {
    "api_key": "sk-ov-key-5678",
    "api_base": "https://api.openai.com/v1",
    "embedding_model": "text-embedding-3-small",
    "vlm_model": "gpt-4o-mini",
    "provider": "openai",
    "dimension": 1536,
}


def _make_installed(settings):
    settings.openviking_dir.mkdir(parents=True, exist_ok=True)


def _make_configured(settings):
    (settings.openviking_home / "ov.conf").parent.mkdir(parents=True, exist_ok=True)
    (settings.openviking_home / "ov.conf").write_text(
        json.dumps({"embedding": {"dense": {"api_key": "sk-ov-key-5678", "api_base": "https://api.openai.com/v1"}}}),
        encoding="utf-8",
    )


def test_status_not_installed(client, auth_headers, runner):
    payload = assert_ok(client.get("/api/openviking/status", headers=auth_headers))
    data = payload["data"]
    assert data["installed"] is False
    assert data["config_ready"] is False
    assert data["endpoint"] == "http://127.0.0.1:1933"


def test_status_installed_configured_healthy(client, auth_headers, runner, fake_httpx, settings):
    _make_installed(settings)
    _make_configured(settings)
    set_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT", "http://127.0.0.1:1933")
    fake_httpx.add("GET", "/stats", httpx.Response(200, json={"chunks": 5}))
    payload = assert_ok(client.get("/api/openviking/status", headers=auth_headers))
    data = payload["data"]
    assert data["installed"] is True
    assert data["config_ready"] is True
    assert data["service_active"] is True
    assert data["healthy"] is True
    assert data["wired_into_hermes"] is True


def test_install_returns_202_and_runs_installer(client, auth_headers, runner, settings):
    payload = assert_ok(client.post("/api/openviking/install", headers=auth_headers), 202)
    assert "install" in payload["data"]["message"].lower()
    assert runner.called_with("bash", str(settings.openviking_install_script))


def test_config_get_unconfigured(client, auth_headers):
    payload = assert_ok(client.get("/api/openviking/config", headers=auth_headers))
    assert payload["data"] == {"configured": False}


def test_config_post_then_get_masks_key(client, auth_headers, settings):
    created = assert_ok(client.post("/api/openviking/config", headers=auth_headers, json=OV_CONFIG_BODY))
    assert created["data"] == {"configured": True, "api_base": "https://api.openai.com/v1"}
    payload = assert_ok(client.get("/api/openviking/config", headers=auth_headers))
    data = payload["data"]
    assert data["configured"] is True
    assert data["api_key"] == "sk-****5678"
    assert data["embedding_model"] == "text-embedding-3-small"
    assert data["vlm_model"] == "gpt-4o-mini"
    assert "sk-ov-key-5678" not in str(payload)
    # The one key feeds both embedding and VLM. / Một key cấp cho cả embedding và VLM.
    raw = json.loads((settings.openviking_home / "ov.conf").read_text(encoding="utf-8"))
    assert raw["vlm"]["api_key"] == raw["embedding"]["dense"]["api_key"] == "sk-ov-key-5678"


def test_config_post_empty_body_422(client, auth_headers):
    response = client.post("/api/openviking/config", headers=auth_headers, json={})
    assert response.status_code == 422


def test_test_key(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/v1/models", httpx.Response(200, json={"data": []}))
    payload = assert_ok(
        client.post("/api/openviking/test-key", headers=auth_headers, json={"api_key": "sk-anything"}),
    )
    assert payload["data"] == {"status_code": 200}


def test_test_key_network_error_502(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/v1/models", httpx.ConnectError("down"))
    assert_fail(client.post("/api/openviking/test-key", headers=auth_headers, json={"api_key": "sk-x"}), 502)


def test_enable_not_installed_409(client, auth_headers):
    assert_fail(client.post("/api/openviking/enable", headers=auth_headers), 409)


def test_enable_not_configured_409(client, auth_headers, settings):
    _make_installed(settings)
    assert_fail(client.post("/api/openviking/enable", headers=auth_headers), 409)


def test_enable_happy(client, auth_headers, runner, settings):
    _make_installed(settings)
    _make_configured(settings)
    payload = assert_ok(client.post("/api/openviking/enable", headers=auth_headers))
    assert payload["data"]["enabled"] is True
    assert get_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT") == "http://127.0.0.1:1933"
    assert runner.called_with("systemctl", "start", "hermes-openviking.service")
    assert runner.called_with("systemctl", "restart", "hermes-gateway")


def test_disable_unwires_endpoint(client, auth_headers, runner, settings):
    _make_installed(settings)
    set_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT", "http://127.0.0.1:1933")
    payload = assert_ok(client.post("/api/openviking/disable", headers=auth_headers))
    assert payload["data"] == {"disabled": True}
    assert get_env_value(settings.mgmt_env_file, "OPENVIKING_ENDPOINT") is None
    assert runner.called_with("systemctl", "stop", "hermes-openviking.service")


def test_restart_not_installed_409(client, auth_headers):
    assert_fail(client.post("/api/openviking/restart", headers=auth_headers), 409)


def test_restart_happy(client, auth_headers, runner, settings):
    _make_installed(settings)
    payload = assert_ok(client.post("/api/openviking/restart", headers=auth_headers))
    assert payload["data"] == {"restarted": True}
    assert runner.called_with("systemctl", "restart", "hermes-openviking.service")


def test_upgrade_not_installed_409(client, auth_headers):
    assert_fail(client.post("/api/openviking/upgrade", headers=auth_headers), 409)


def test_upgrade_202_when_installed(client, auth_headers, runner, settings):
    _make_installed(settings)
    payload = assert_ok(client.post("/api/openviking/upgrade", headers=auth_headers), 202)
    assert "upgrade" in payload["data"]["message"].lower()
    assert runner.called_with("bash", "-c")


def test_uninstall_purge_removes_dirs(client, auth_headers, runner, settings):
    _make_installed(settings)
    _make_configured(settings)
    payload = assert_ok(
        client.post("/api/openviking/uninstall", headers=auth_headers, json={"purge": True}),
        202,
    )
    assert payload["data"]["purge"] is True
    assert not settings.openviking_dir.exists()
    assert not settings.openviking_home.exists()
    assert runner.called_with("bash", str(settings.openviking_uninstall_script))


def test_stats_reports_data_dir(client, auth_headers, runner, fake_httpx, settings):
    _make_installed(settings)
    data_dir = settings.openviking_home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "rag.bin").write_bytes(b"12345")
    fake_httpx.add("GET", "/stats", httpx.Response(200, json={"chunks": 3}))
    payload = assert_ok(client.get("/api/openviking/stats", headers=auth_headers))
    data = payload["data"]
    assert data["data_size_mb"] == 0.0  # 5 bytes rounds to 0.0 MB. / 5 byte làm tròn thành 0.0 MB.
    assert data["server_stats"] == {"chunks": 3}
    assert str(data_dir) == data["data_dir"]


def test_logs_tail(client, auth_headers, runner):
    runner.set_result("journalctl", stdout="ov line\n")
    payload = assert_ok(client.get("/api/openviking/logs?lines=10", headers=auth_headers))
    assert payload["data"]["service"] == "hermes-openviking.service"
    assert payload["data"]["entries"] == ["ov line"]
