"""Codex OAuth + roles/rule-groups tests. / Test Codex OAuth + vai trò/nhóm quy tắc."""

from __future__ import annotations

import json

from conftest import RULE_GROUPS, assert_fail, assert_ok
from hermes_mgmt.hermes_fs import read_config_yaml


def _write_auth(settings, data):
    path = settings.hermes_home / "auth.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# --- Codex -------------------------------------------------------------------


def test_codex_status_disconnected(client, auth_headers):
    payload = assert_ok(client.get("/api/codex/auth/status", headers=auth_headers))
    assert payload["data"] == {"status": "disconnected"}


def test_codex_start_returns_device_code(client, auth_headers, runner):
    runner.set_result(
        "hermes",
        "auth",
        "add",
        stdout="Open https://auth.openai.com/codex/device?flow=abc and enter code 41R1-F6HE\n",
    )
    payload = assert_ok(client.post("/api/codex/auth/start", headers=auth_headers))
    assert payload["data"] == {
        "status": "pending",
        "url": "https://auth.openai.com/codex/device?flow=abc",
        "code": "41R1-F6HE",
    }
    assert runner.called_with("hermes", "auth", "add", "openai-codex", "--headless")


def test_codex_status_pending_after_start(client, auth_headers, runner):
    runner.set_result("hermes", "auth", "add", stdout="visit https://x.test/p code 1234-ABCD\n")
    client.post("/api/codex/auth/start", headers=auth_headers)
    payload = assert_ok(client.get("/api/codex/auth/status", headers=auth_headers))
    assert payload["data"]["status"] == "pending"
    assert payload["data"]["code"] == "1234-ABCD"


def test_codex_status_connected_via_auth_json(client, auth_headers, runner, settings):
    _write_auth(settings, {"openai-codex": {"access_token": "tok"}})
    payload = assert_ok(client.get("/api/codex/auth/status", headers=auth_headers))
    assert payload["data"] == {"status": "connected", "model_set": True}
    config = read_config_yaml(settings.hermes_home / "config.yaml")
    assert config["model"]["provider"] == "codex"
    assert runner.called_with("systemctl", "restart", "hermes-gateway")


def test_codex_import_happy(client, auth_headers, runner, settings):
    payload = assert_ok(
        client.post(
            "/api/codex/auth/import",
            headers=auth_headers,
            json={"auth_json": '{"openai-codex": {"token": "x"}}'},
        ),
    )
    assert payload["data"]["imported"] is True
    saved = json.loads((settings.hermes_home / "auth.json").read_text(encoding="utf-8"))
    assert "openai-codex" in saved
    assert read_config_yaml(settings.hermes_home / "config.yaml")["model"]["provider"] == "codex"


def test_codex_import_accepts_dict(client, auth_headers, runner, settings):
    payload = assert_ok(
        client.post(
            "/api/codex/auth/import",
            headers=auth_headers,
            json={"auth_json": {"codex": {"token": "y"}}},
        ),
    )
    assert payload["data"]["imported"] is True


def test_codex_import_invalid_json_400(client, auth_headers):
    assert_fail(
        client.post("/api/codex/auth/import", headers=auth_headers, json={"auth_json": "{not json"}),
        400,
    )


def test_codex_import_without_codex_entry_400(client, auth_headers):
    assert_fail(
        client.post("/api/codex/auth/import", headers=auth_headers, json={"auth_json": '{"foo": 1}'}),
        400,
    )


def test_codex_disable_repoints_provider(client, auth_headers, runner, settings):
    _write_auth(settings, {"openai-codex": {"token": "x"}, "active_provider": "openai-codex"})
    payload = assert_ok(
        client.post("/api/codex/auth/disable", headers=auth_headers, json={"to_provider": "deepseek"}),
    )
    assert payload["data"] == {"disabled": True, "model_provider": "deepseek"}
    saved = json.loads((settings.hermes_home / "auth.json").read_text(encoding="utf-8"))
    assert "openai-codex" not in saved
    assert "active_provider" not in saved
    assert read_config_yaml(settings.hermes_home / "config.yaml")["model"]["provider"] == "deepseek"
    assert runner.called_with("hermes", "auth", "remove", "openai-codex")


def test_codex_requires_auth(client):
    assert_fail(client.get("/api/codex/auth/status"), 401)


# --- Rules -------------------------------------------------------------------


def test_rules_list_all_groups(client, auth_headers):
    payload = assert_ok(client.get("/api/rules", headers=auth_headers))
    assert payload["data"]["count"] == 8
    ids = [group["id"] for group in payload["data"]["groups"]]
    assert ids == sorted(RULE_GROUPS)
    first = payload["data"]["groups"][0]
    assert first["title"] == f"Rule {first['id']}"
    assert first["body"].startswith("# ")


def test_rule_detail(client, auth_headers):
    payload = assert_ok(client.get("/api/rules/a-identity", headers=auth_headers))
    assert payload["data"]["id"] == "a-identity"
    assert "Noi dung quy tac a-identity." in payload["data"]["body"]


def test_rule_unknown_404(client, auth_headers):
    assert_fail(client.get("/api/rules/zzz-unknown", headers=auth_headers), 404)


# --- Roles -------------------------------------------------------------------


def test_roles_list_includes_presets(client, auth_headers):
    payload = assert_ok(client.get("/api/roles", headers=auth_headers))
    roles = payload["data"]["roles"]
    assert payload["data"]["active_role_id"] is None
    by_id = {role["id"]: role for role in roles}
    assert set(by_id) == {"cskh", "sales"}
    assert by_id["cskh"]["source"] == "preset"
    assert by_id["cskh"]["label"] == "CSKH"
    assert by_id["cskh"]["rules"] == ["a-identity", "b-account-safety"]
    assert "Ban la nhan vien CSKH." in by_id["cskh"]["persona"]


def test_role_detail_preset(client, auth_headers):
    payload = assert_ok(client.get("/api/roles/cskh", headers=auth_headers))
    assert payload["data"]["source"] == "preset"
    assert payload["data"]["tone"] == "friendly"


def test_role_detail_unknown_404(client, auth_headers):
    assert_fail(client.get("/api/roles/ghost", headers=auth_headers), 404)


def test_active_role_404_before_apply(client, auth_headers):
    assert_fail(client.get("/api/roles/active", headers=auth_headers), 404)


def test_role_create_custom_drops_unknown_rules(client, auth_headers, settings):
    payload = assert_ok(
        client.post(
            "/api/roles",
            headers=auth_headers,
            json={"id": "helper", "persona": "You help users.", "label": "Helper", "rules": ["a-identity", "zzz"]},
        ),
    )
    assert payload["data"]["source"] == "custom"
    assert payload["data"]["rules"] == ["a-identity"]
    assert (settings.hermes_home / "roles" / "helper.yaml").exists()
    listed = assert_ok(client.get("/api/roles", headers=auth_headers))
    assert "helper" in {role["id"] for role in listed["data"]["roles"]}


def test_role_create_shadowing_preset_409(client, auth_headers):
    assert_fail(
        client.post("/api/roles", headers=auth_headers, json={"id": "cskh", "persona": "hijack"}),
        409,
    )


def test_role_create_empty_body_422(client, auth_headers):
    response = client.post("/api/roles", headers=auth_headers, json={})
    assert response.status_code == 422


def test_role_create_invalid_id_422(client, auth_headers):
    response = client.post("/api/roles", headers=auth_headers, json={"id": "Bad Id", "persona": "x"})
    assert response.status_code == 422


def test_role_delete_preset_403(client, auth_headers):
    assert_fail(client.delete("/api/roles/cskh", headers=auth_headers), 403)


def test_role_delete_custom_roundtrip(client, auth_headers):
    client.post("/api/roles", headers=auth_headers, json={"id": "helper", "persona": "p"})
    assert_ok(client.delete("/api/roles/helper", headers=auth_headers))
    assert_fail(client.delete("/api/roles/helper", headers=auth_headers), 404)


def test_role_apply_writes_persona_and_restarts(client, auth_headers, runner, settings):
    payload = assert_ok(client.post("/api/roles/cskh/apply", headers=auth_headers))
    data = payload["data"]
    assert data["id"] == "cskh"
    assert data["rules"] == ["a-identity", "b-account-safety"]
    assert "Ban la nhan vien CSKH." in data["persona_preview"]
    assert "Noi dung quy tac a-identity." in data["persona_preview"]
    assert "Noi dung quy tac b-account-safety." in data["persona_preview"]
    persona = (settings.hermes_home / "persona.md").read_text(encoding="utf-8")
    assert persona == data["persona_preview"]
    active = json.loads((settings.hermes_home / "active_role.json").read_text(encoding="utf-8"))
    assert active["id"] == "cskh"
    assert active["rules"] == ["a-identity", "b-account-safety"]
    assert runner.called_with("systemctl", "restart", "hermes-gateway")


def test_active_role_after_apply(client, auth_headers, runner):
    client.post("/api/roles/sales/apply", headers=auth_headers)
    payload = assert_ok(client.get("/api/roles/active", headers=auth_headers))
    assert payload["data"]["id"] == "sales"
    listed = assert_ok(client.get("/api/roles", headers=auth_headers))
    assert listed["data"]["active_role_id"] == "sales"


def test_role_apply_unknown_404(client, auth_headers):
    assert_fail(client.post("/api/roles/ghost/apply", headers=auth_headers), 404)
