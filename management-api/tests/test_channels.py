"""Messaging-channel tests. / Test kênh nhắn tin."""

from __future__ import annotations

from conftest import CHANNELS, assert_fail, assert_ok
from hermes_mgmt.hermes_fs import read_config_yaml, write_config_yaml


def test_list_channels_shape(client, auth_headers):
    payload = assert_ok(client.get("/api/channels", headers=auth_headers))
    items = payload["data"]["channels"]
    assert [item["id"] for item in items] == list(CHANNELS)
    for item in items:
        assert item["configured"] is False
        assert "config" not in item
        assert item["required_fields"]
    telegram = items[0]
    assert telegram["required_fields"] == ["token", "chat_id"]
    assert telegram["label_vi"] == "telegram VI"


def test_put_channel_empty_body_422(client, auth_headers):
    response = client.put("/api/channels/telegram", headers=auth_headers, json={})
    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert "missing required fields" in payload["error"]


def test_put_channel_missing_one_field_422(client, auth_headers):
    response = client.put("/api/channels/telegram", headers=auth_headers, json={"token": "t-123"})
    assert response.status_code == 422


def test_put_channel_happy(client, auth_headers, settings):
    payload = assert_ok(
        client.put(
            "/api/channels/telegram",
            headers=auth_headers,
            json={"token": "t-123", "chat_id": "42", "extra_note": "keep"},
        ),
    )
    assert payload["data"]["id"] == "telegram"
    config = read_config_yaml(settings.hermes_home / "config.yaml")
    assert config["channels"]["telegram"] == {"token": "t-123", "chat_id": "42", "extra_note": "keep"}


def test_put_channel_unknown_404(client, auth_headers):
    assert_fail(client.put("/api/channels/carrier-pigeon", headers=auth_headers, json={"token": "x"}), 404)


def test_put_channel_requires_auth(client, auth_headers):
    assert_fail(client.put("/api/channels/telegram", headers=auth_headers | {"Authorization": "Bearer bad"}), 401)


def test_list_shows_configured_with_masked_secret(client, auth_headers, settings):
    write_config_yaml(
        settings.hermes_home / "config.yaml",
        {"channels": {"discord": {"bot_token": "bot-secret-9988"}}},
    )
    payload = assert_ok(client.get("/api/channels", headers=auth_headers))
    discord = next(item for item in payload["data"]["channels"] if item["id"] == "discord")
    assert discord["configured"] is True
    assert discord["config"]["bot_token"] == "sk-****9988"
    assert "bot-secret-9988" not in str(payload)


def test_delete_channel_happy(client, auth_headers, settings):
    write_config_yaml(
        settings.hermes_home / "config.yaml",
        {"channels": {"slack": {"bot_token": "b", "app_token": "a"}}},
    )
    payload = assert_ok(client.delete("/api/channels/slack", headers=auth_headers))
    assert payload["data"]["deleted"] is True
    config = read_config_yaml(settings.hermes_home / "config.yaml")
    assert "slack" not in config.get("channels", {})


def test_delete_channel_not_configured_404(client, auth_headers):
    assert_fail(client.delete("/api/channels/telegram", headers=auth_headers), 404)


def test_delete_channel_unknown_404(client, auth_headers):
    assert_fail(client.delete("/api/channels/carrier-pigeon", headers=auth_headers), 404)
