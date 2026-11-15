"""Health + info/status/version/system/domain tests. / Test health + info/status/version/system/domain."""

from __future__ import annotations

from conftest import AUTH_TOKEN, assert_fail, assert_ok, write_env


def test_health_needs_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    # /health is NOT data-enveloped per README. / /health không bọc data theo README.
    assert payload == {"ok": True, "version": "0.1.0"}


def test_health_rejects_bearer_garbage_but_still_public(client):
    response = client.get("/health", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_info_requires_auth(client):
    response = client.get("/api/info")
    assert_fail(response, 401)


def test_info_happy(client, auth_headers, runner, settings):
    runner.set_result("hermes", "version", stdout="Hermes Agent v0.13.0\n")
    payload = assert_ok(client.get("/api/info", headers=auth_headers))
    data = payload["data"]
    assert data["domain"] == "test.example.com"
    assert data["ip"] == "203.0.113.10"
    assert data["hermes_version"] == "Hermes Agent v0.13.0"
    assert data["mgmt_version"] == "0.1.0"
    assert data["dashboard_url"] == f"https://test.example.com/?token={AUTH_TOKEN}"
    assert data["auth_token"] == AUTH_TOKEN
    assert runner.called_with("hermes", "version")


def test_info_null_token_when_unset(client, auth_headers, runner, settings):
    write_env(settings, "HERMES_AUTH_TOKEN", "")
    runner.set_result("hermes", "version", stdout="v1")
    payload = assert_ok(client.get("/api/info", headers=auth_headers))
    assert payload["data"]["auth_token"] is None
    assert payload["data"]["dashboard_url"] is None


def test_info_ip_fallback_when_env_missing(client, auth_headers, runner, settings):
    from hermes_mgmt.env_file import delete_env_value

    delete_env_value(settings.mgmt_env_file, "HERMES_DROPLET_IP")
    runner.set_result("hermes", "version", stdout="v1")
    payload = assert_ok(client.get("/api/info", headers=auth_headers))
    ip = payload["data"]["ip"]
    assert isinstance(ip, str) and ip


def test_status_all_services_active(client, auth_headers, runner):
    runner.set_result("systemctl", "is-active", stdout="active\n", exit_code=0)
    payload = assert_ok(client.get("/api/status", headers=auth_headers))
    services = payload["data"]["services"]
    assert set(services) == {
        "hermes-gateway.service",
        "hermes-dashboard.service",
        "hermes-mgmt.service",
        "caddy.service",
    }
    for unit, state in services.items():
        assert state["active"] is True, unit
        assert state["state"] == "active", unit


def test_status_reports_inactive_unit(client, auth_headers, runner):
    runner.set_result("systemctl", "is-active", stdout="inactive\n", exit_code=3)
    payload = assert_ok(client.get("/api/status", headers=auth_headers))
    for unit, state in payload["data"]["services"].items():
        assert state["active"] is False, unit
        assert state["state"] == "inactive", unit


def test_version_passthrough(client, auth_headers, runner):
    runner.set_result("hermes", "version", stdout="Hermes CLI v9.9\n", exit_code=0)
    payload = assert_ok(client.get("/api/version", headers=auth_headers))
    assert payload["data"] == {"output": "Hermes CLI v9.9", "exit_code": 0}


def test_version_failure_exit_code(client, auth_headers, runner):
    runner.set_result("hermes", "version", stdout="", stderr="boom\n", exit_code=1)
    payload = assert_ok(client.get("/api/version", headers=auth_headers))
    assert payload["data"]["exit_code"] == 1
    assert payload["data"]["output"] == "boom"


def test_system_shape(client, auth_headers):
    payload = assert_ok(client.get("/api/system", headers=auth_headers))
    data = payload["data"]
    assert set(data) == {"cpu_percent", "memory", "disk", "uptime_seconds", "load_avg"}
    assert set(data["memory"]) == {"total", "available", "percent"}
    assert set(data["disk"]) == {"total", "used", "percent"}
    assert len(data["load_avg"]) == 3
    assert data["uptime_seconds"] >= 0


def test_domain_get(client, auth_headers):
    payload = assert_ok(client.get("/api/domain", headers=auth_headers))
    assert payload["data"] == {"domain": "test.example.com"}


def test_domain_put_updates_env_and_restarts_caddy(client, auth_headers, runner, settings):
    payload = assert_ok(
        client.put("/api/domain", headers=auth_headers, json={"domain": "new.example.com"}),
    )
    assert payload["data"]["domain"] == "new.example.com"
    assert runner.called_with("systemctl", "restart", "caddy")
    assert not runner.called_with("caddy", "reload")
    from hermes_mgmt.env_file import get_env_value

    assert get_env_value(settings.mgmt_env_file, "DOMAIN") == "new.example.com"


def test_domain_put_reloads_caddyfile_when_present(client, auth_headers, runner, settings):
    caddyfile = settings.install_dir / "Caddyfile"
    caddyfile.parent.mkdir(parents=True, exist_ok=True)
    caddyfile.write_text("{$DOMAIN}\n", encoding="utf-8")
    assert_ok(client.put("/api/domain", headers=auth_headers, json={"domain": "x.example.com"}))
    assert runner.called_with("caddy", "reload")


def test_domain_put_rejects_empty_body(client, auth_headers):
    response = client.put("/api/domain", headers=auth_headers, json={})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_unknown_route_returns_envelope_404(client, auth_headers):
    response = client.get("/api/definitely-not-a-route", headers=auth_headers)
    assert_fail(response, 404)
