"""Zalo sidecar proxy tests. / Test proxy sidecar Zalo."""

from __future__ import annotations

import httpx

from conftest import assert_fail, assert_ok, write_env
from hermes_mgmt.env_file import delete_env_value, get_env_value


def test_status_sidecar_down(client, auth_headers, fake_httpx):
    payload = assert_ok(client.get("/api/zalo/status", headers=auth_headers))
    data = payload["data"]
    assert data["status"] == "error"
    assert data["sidecar"] is False
    assert data["owner_set"] is False


def test_status_disconnected(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/status", httpx.Response(200, json={"status": "disconnected"}))
    payload = assert_ok(client.get("/api/zalo/status", headers=auth_headers))
    assert payload["data"]["status"] == "disconnected"
    assert payload["data"]["sidecar"] is True
    assert payload["data"]["owner_set"] is False


def test_status_connected_and_owner_set(client, auth_headers, fake_httpx, settings):
    write_env(settings, "ZALO_PERSONAL_OWNER_UID", "boss-1")
    fake_httpx.add(
        "GET",
        "/status",
        httpx.Response(200, json={"status": "connected", "bot_uid": "555", "name": "Bot"}),
    )
    payload = assert_ok(client.get("/api/zalo/status", headers=auth_headers))
    data = payload["data"]
    assert data["status"] == "connected"
    assert data["bot_uid"] == "555"
    assert data["name"] == "Bot"
    assert data["owner_set"] is True


def test_connect_returns_qr_url(client, auth_headers, fake_httpx):
    fake_httpx.add("POST", "/login/qr", httpx.Response(200, json={"status": "pending"}))
    payload = assert_ok(client.post("/api/zalo/connect", headers=auth_headers))
    assert payload["data"] == {"status": "pending", "qr_url": "/api/zalo/qr"}


def test_connect_when_already_connected(client, auth_headers, fake_httpx):
    fake_httpx.add("POST", "/login/qr", httpx.Response(200, json={"status": "connected", "bot_uid": "555"}))
    payload = assert_ok(client.post("/api/zalo/connect", headers=auth_headers))
    assert payload["data"] == {"status": "connected", "bot_uid": "555"}


def test_connect_sidecar_down_503(client, auth_headers, fake_httpx):
    assert_fail(client.post("/api/zalo/connect", headers=auth_headers), 503)


def test_qr_png_passthrough(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/qr.png", httpx.Response(200, content=b"\x89PNG-bytes"))
    response = client.get("/api/zalo/qr", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"\x89PNG-bytes"


def test_qr_not_ready_404(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/qr.png", httpx.Response(404, json={"error": "generating"}))
    assert_fail(client.get("/api/zalo/qr", headers=auth_headers), 404)


def test_set_owner_by_phone(client, auth_headers, fake_httpx, runner, settings):
    fake_httpx.add("POST", "/users/by-phones", httpx.Response(200, json={"users": [{"uid": "boss-1"}]}))
    fake_httpx.add("GET", "/status", httpx.Response(200, json={"status": "connected", "bot_uid": "555"}))
    payload = assert_ok(client.post("/api/zalo/set-owner", headers=auth_headers, json={"phone": "0912345678"}))
    assert payload["data"] == {"owner_uid": "boss-1", "owner_set": True}
    assert get_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID") == "boss-1"
    assert runner.called_with("systemctl", "restart", "hermes-gateway")


def test_set_owner_by_uid(client, auth_headers, fake_httpx, runner, settings):
    fake_httpx.add("GET", "/status", httpx.Response(200, json={"status": "connected", "uid": "boss-9"}))
    payload = assert_ok(client.post("/api/zalo/set-owner", headers=auth_headers, json={"uid": "boss-9"}))
    assert payload["data"]["owner_uid"] == "boss-9"
    assert get_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID") == "boss-9"


def test_set_owner_unknown_phone_404(client, auth_headers, fake_httpx):
    fake_httpx.add("POST", "/users/by-phones", httpx.Response(200, json={"users": []}))
    assert_fail(client.post("/api/zalo/set-owner", headers=auth_headers, json={"phone": "000"}), 404)


def test_set_owner_bot_not_logged_in_409(client, auth_headers, fake_httpx):
    fake_httpx.add("POST", "/users/by-phones", httpx.Response(200, json={"users": [{"uid": "boss-1"}]}))
    fake_httpx.add("GET", "/status", httpx.Response(200, json={"status": "disconnected"}))
    assert_fail(client.post("/api/zalo/set-owner", headers=auth_headers, json={"phone": "0912345678"}), 409)


def test_set_owner_empty_body_422(client, auth_headers, fake_httpx):
    response = client.post("/api/zalo/set-owner", headers=auth_headers, json={})
    assert response.status_code == 422


def test_owner_get(client, auth_headers, settings):
    payload = assert_ok(client.get("/api/zalo/owner", headers=auth_headers))
    assert payload["data"] == {"owner_uid": None, "owner_set": False}
    write_env(settings, "ZALO_PERSONAL_OWNER_UID", "boss-7")
    payload = assert_ok(client.get("/api/zalo/owner", headers=auth_headers))
    assert payload["data"] == {"owner_uid": "boss-7", "owner_set": True}


def test_disconnect_clears_owner(client, auth_headers, fake_httpx, settings):
    write_env(settings, "ZALO_PERSONAL_OWNER_UID", "boss-1")
    fake_httpx.add("POST", "/logout", httpx.Response(200, json={"ok": True}))
    payload = assert_ok(client.post("/api/zalo/disconnect", headers=auth_headers))
    assert payload["data"] == {"disconnected": True}
    assert get_env_value(settings.mgmt_env_file, "ZALO_PERSONAL_OWNER_UID") is None
    assert ("POST", "/logout") in fake_httpx.calls
