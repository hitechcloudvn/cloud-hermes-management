"""Service control tests (restart/stop/start/rebuild/upgrade/reset). / Test điều khiển dịch vụ."""

from __future__ import annotations

import yaml

from conftest import assert_fail, assert_ok


def test_control_requires_auth(client):
    assert_fail(client.post("/api/restart"), 401)
    assert_fail(client.post("/api/stop"), 401)
    assert_fail(client.post("/api/start"), 401)
    assert_fail(client.post("/api/rebuild"), 401)


def test_restart_all(client, auth_headers, runner):
    payload = assert_ok(client.post("/api/restart", headers=auth_headers))
    assert "restarted" in payload["data"]["message"]
    assert runner.called_with("systemctl", "restart", "hermes.target")


def test_stop_all(client, auth_headers, runner):
    assert_ok(client.post("/api/stop", headers=auth_headers))
    assert runner.called_with("systemctl", "stop", "hermes.target")


def test_start_all(client, auth_headers, runner):
    assert_ok(client.post("/api/start", headers=auth_headers))
    assert runner.called_with("systemctl", "start", "hermes.target")


def test_restart_failure_returns_500(client, auth_headers, runner):
    runner.set_result("systemctl", "restart", exit_code=1, stderr="unit failed\n")
    assert_fail(client.post("/api/restart", headers=auth_headers), 500)


def test_rebuild_happy(client, auth_headers, runner, settings):
    payload = assert_ok(client.post("/api/rebuild", headers=auth_headers))
    assert "rebuilt" in payload["data"]["message"]
    assert runner.called_with("npm", "install")
    assert runner.called_with("npm", "run", "build")
    assert runner.called_with("systemctl", "restart", "hermes-dashboard")


def test_rebuild_npm_install_failure(client, auth_headers, runner):
    runner.set_result("npm", "install", exit_code=1, stderr="npm exploded\n")
    assert_fail(client.post("/api/rebuild", headers=auth_headers), 500)


def test_rebuild_npm_build_failure(client, auth_headers, runner):
    runner.set_result("npm", "run", exit_code=1, stderr="build failed\n")
    assert_fail(client.post("/api/rebuild", headers=auth_headers), 500)


def test_upgrade_returns_202_and_runs_in_background(client, auth_headers, runner):
    payload = assert_ok(client.post("/api/upgrade", headers=auth_headers), 202)
    assert "upgrade" in payload["data"]["message"].lower()
    # Background task already executed by TestClient. / TestClient đã chạy task nền.
    assert runner.called_with("git")
    assert runner.called_with("uv", "pip", "install")
    assert runner.called_with("systemctl", "restart", "hermes-gateway", "hermes-dashboard")


def test_upgrade_mgmt_curl_fallback_without_git(client, auth_headers, runner, settings):
    payload = assert_ok(client.post("/api/upgrade-mgmt", headers=auth_headers), 202)
    assert "upgrade" in payload["data"]["message"].lower()
    assert runner.called_with("curl", "-fsSL")
    assert runner.called_with("uv", "pip", "install")
    assert runner.called_with("systemctl", "restart", "hermes-mgmt")


def test_upgrade_mgmt_uses_git_when_available(client, auth_headers, runner, settings):
    (settings.mgmt_dir / ".git").mkdir()
    assert_ok(client.post("/api/upgrade-mgmt", headers=auth_headers), 202)
    assert runner.called_with("git")
    assert not runner.called_with("curl")


def test_reset_requires_exact_confirm(client, auth_headers, settings):
    response = client.post("/api/reset", headers=auth_headers, json={"confirm": "reset"})
    assert_fail(response, 400)
    response = client.post("/api/reset", headers=auth_headers, json={})
    assert response.status_code == 422


def test_reset_wipes_config_and_sessions(client, auth_headers, settings):
    config_path = settings.hermes_home / "config.yaml"
    config_path.write_text("model:\n  provider: deepseek\n", encoding="utf-8")
    sessions = settings.hermes_home / "sessions"
    sessions.mkdir()
    (sessions / "s1.json").write_text("{}", encoding="utf-8")

    payload = assert_ok(client.post("/api/reset", headers=auth_headers, json={"confirm": "RESET"}))
    assert "wiped" in payload["data"]["message"]
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) in ({}, None)
    assert not sessions.exists()
    # Env file survives the reset. / File env còn nguyên sau reset.
    assert "HERMES_MGMT_API_KEY" in settings.mgmt_env_file.read_text(encoding="utf-8")
