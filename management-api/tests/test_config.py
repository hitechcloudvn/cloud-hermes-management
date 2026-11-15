"""Config + provider + API-key tests. / Test cấu hình + nhà cung cấp + API key."""

from __future__ import annotations

import httpx

from conftest import PROVIDERS, assert_fail, assert_ok, write_env
from hermes_mgmt.env_file import get_env_value
from hermes_mgmt.hermes_fs import read_config_yaml, write_config_yaml


def test_config_requires_auth(client):
    assert_fail(client.get("/api/config"), 401)


def test_get_config_masks_sensitive_values(client, auth_headers, settings):
    config_path = settings.hermes_home / "config.yaml"
    write_config_yaml(
        config_path,
        {
            "model": {"default": "deepseek/deepseek-v4-flash", "provider": "deepseek"},
            "custom": {"api_key": "sk-secret-abcdef1234", "note": "plain"},
        },
    )
    response = client.get("/api/config", headers=auth_headers)
    payload = assert_ok(response)
    config = payload["data"]["config"]
    assert config["custom"]["api_key"] == "sk-****1234"
    assert config["custom"]["note"] == "plain"
    assert config["model"]["provider"] == "deepseek"
    assert "sk-secret-abcdef1234" not in response.text


def test_get_config_empty_when_missing(client, auth_headers):
    payload = assert_ok(client.get("/api/config", headers=auth_headers))
    assert payload["data"]["config"] == {}


def test_providers_lists_15_templates(client, auth_headers):
    payload = assert_ok(client.get("/api/providers", headers=auth_headers))
    assert payload["data"]["count"] == 15
    ids = [item["id"] for item in payload["data"]["providers"]]
    assert set(ids) == set(PROVIDERS)
    first = payload["data"]["providers"][0]
    assert {"id", "label_vi", "label_en", "base_url", "api_key_env", "models", "website"} <= set(first)


def test_set_provider_normalizes_bare_model(client, auth_headers, settings):
    payload = assert_ok(
        client.put("/api/config/provider", headers=auth_headers, json={"provider": "deepseek", "model": "deepseek-v4-flash"}),
    )
    assert payload["data"] == {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash"}
    config = read_config_yaml(settings.hermes_home / "config.yaml")
    assert config["model"]["default"] == "deepseek/deepseek-v4-flash"
    assert config["model"]["provider"] == "deepseek"


def test_set_provider_prefix_is_idempotent(client, auth_headers, settings):
    body = {"provider": "deepseek", "model": "deepseek/deepseek-v4-flash"}
    first = assert_ok(client.put("/api/config/provider", headers=auth_headers, json=body))
    second = assert_ok(client.put("/api/config/provider", headers=auth_headers, json=body))
    assert first["data"]["model"] == second["data"]["model"] == "deepseek/deepseek-v4-flash"
    config = read_config_yaml(settings.hermes_home / "config.yaml")
    assert config["model"]["default"] == "deepseek/deepseek-v4-flash"


def test_set_provider_empty_body_422(client, auth_headers):
    response = client.put("/api/config/provider", headers=auth_headers, json={})
    assert response.status_code == 422


def test_put_api_key_writes_env_and_restarts_gateway(client, auth_headers, runner, settings):
    payload = assert_ok(
        client.put("/api/config/api-key", headers=auth_headers, json={"provider": "deepseek", "api_key": "sk-new-9876"}),
    )
    assert payload["data"]["saved"] is True
    assert payload["data"]["env_key"] == "DEEPSEEK_API_KEY"
    assert get_env_value(settings.mgmt_env_file, "DEEPSEEK_API_KEY") == "sk-new-9876"
    assert runner.called_with("systemctl", "restart", "hermes-gateway")


def test_delete_api_key_removes_env(client, auth_headers, settings):
    write_env(settings, "DEEPSEEK_API_KEY", "sk-old-1111")
    payload = assert_ok(client.delete("/api/config/api-key?provider=deepseek", headers=auth_headers))
    assert payload["data"]["removed"] is True
    assert get_env_value(settings.mgmt_env_file, "DEEPSEEK_API_KEY") is None


def test_delete_api_key_unknown_provider_404(client, auth_headers):
    assert_fail(client.delete("/api/config/api-key?provider=nonexistent", headers=auth_headers), 404)


def test_delete_api_key_missing_key_is_not_an_error(client, auth_headers):
    payload = assert_ok(client.delete("/api/config/api-key?provider=deepseek", headers=auth_headers))
    assert payload["data"]["removed"] is False


def test_test_key_known_provider(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/v1/models", httpx.Response(200, json={"data": []}))
    payload = assert_ok(
        client.post("/api/config/test-key", headers=auth_headers, json={"provider": "openrouter", "api_key": "sk-or-v1-dummy"}),
    )
    assert payload["data"] == {"status_code": 200, "provider": "openrouter"}
    assert ("GET", "/v1/models") in fake_httpx.calls


def test_test_key_returns_provider_status_even_on_401(client, auth_headers, fake_httpx):
    # Smoke expects 200 even for a dummy key: the provider's verdict is in status_code. / Smoke mong 200 kể cả key giả.
    fake_httpx.add("GET", "/v1/models", httpx.Response(401, json={"error": "bad key"}))
    payload = assert_ok(
        client.post("/api/config/test-key", headers=auth_headers, json={"provider": "deepseek", "api_key": "sk-dead"}),
    )
    assert payload["data"]["status_code"] == 401


def test_test_key_unknown_provider(client, auth_headers, fake_httpx):
    assert_fail(
        client.post("/api/config/test-key", headers=auth_headers, json={"provider": "nonexistent", "api_key": "x"}),
        404,
    )


def test_test_key_network_error_502(client, auth_headers, fake_httpx):
    fake_httpx.add("GET", "/v1/models", httpx.ConnectError("connection refused"))
    assert_fail(
        client.post("/api/config/test-key", headers=auth_headers, json={"provider": "deepseek", "api_key": "sk-x"}),
        502,
    )


def test_test_key_empty_body_422(client, auth_headers):
    response = client.post("/api/config/test-key", headers=auth_headers, json={})
    assert response.status_code == 422
