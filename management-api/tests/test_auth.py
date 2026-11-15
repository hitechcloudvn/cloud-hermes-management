"""Auth + user-account tests. / Test xác thực + quản lý user."""

from __future__ import annotations

from conftest import assert_fail, assert_ok, login, seed_user


def test_login_wrong_password_envelope_401(client, settings):
    seed_user(settings, "alice", "goodpass")
    response = login(client, "alice", "wrongpass")
    assert_fail(response, 401)


def test_login_unknown_user_401(client):
    assert_fail(login(client, "ghost", "whatever"), 401)


def test_login_empty_body_422(client):
    response = client.post("/api/auth/login", json={})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_login_happy_sets_session_cookie(client, settings):
    seed_user(settings, "alice", "goodpass")
    payload = assert_ok(login(client, "alice", "goodpass"))
    assert payload["data"] == {"username": "alice"}
    assert "hermes_mgmt_session" in client.cookies
    who = assert_ok(client.get("/api/auth/user"))
    assert who["data"] == {"username": "alice"}


def test_auth_user_with_bearer_is_root(client, auth_headers):
    payload = assert_ok(client.get("/api/auth/user", headers=auth_headers))
    assert payload["data"] == {"username": "root"}


def test_auth_user_without_credentials_401(client):
    assert_fail(client.get("/api/auth/user"), 401)


def test_logout_is_idempotent(client, settings):
    seed_user(settings, "alice", "goodpass")
    login(client, "alice", "goodpass")
    first = assert_ok(client.post("/api/auth/logout"))
    assert first["data"] == {"logged_out": True}
    second = assert_ok(client.post("/api/auth/logout"))
    assert second["data"] == {"logged_out": True}


def test_create_user_requires_auth(client):
    assert_fail(client.post("/api/auth/create-user", json={"username": "u", "password": "p"}), 401)


def test_create_user_happy_and_duplicate(client, auth_headers, settings):
    created = assert_ok(
        client.post("/api/auth/create-user", headers=auth_headers, json={"username": "bob", "password": "secret1"}),
    )
    assert created["data"]["created"] is True
    duplicate = client.post("/api/auth/create-user", headers=auth_headers, json={"username": "bob", "password": "x1"})
    assert_fail(duplicate, 409)
    assert_ok(login(client, "bob", "secret1"))


def test_create_user_empty_body_422(client, auth_headers):
    response = client.post("/api/auth/create-user", headers=auth_headers, json={})
    assert response.status_code == 422


def test_change_password_empty_body_422(client, auth_headers):
    response = client.put("/api/auth/change-password", headers=auth_headers, json={})
    assert response.status_code == 422


def test_change_password_wrong_old_400(client, auth_headers, settings):
    seed_user(settings, "admin", "oldpass123")
    response = client.put(
        "/api/auth/change-password",
        headers=auth_headers,
        json={"old_password": "not-it", "new_password": "newpass456"},
    )
    assert_fail(response, 400)


def test_change_password_bearer_targets_admin(client, auth_headers, settings):
    seed_user(settings, "admin", "oldpass123")
    payload = assert_ok(
        client.put(
            "/api/auth/change-password",
            headers=auth_headers,
            json={"old_password": "oldpass123", "new_password": "newpass456"},
        ),
    )
    assert payload["data"]["username"] == "admin"
    assert_fail(login(client, "admin", "oldpass123"), 401)
    assert_ok(login(client, "admin", "newpass456"))


def test_change_password_for_session_user(client, settings):
    seed_user(settings, "alice", "alicepass")
    login(client, "alice", "alicepass")
    payload = assert_ok(
        client.put("/api/auth/change-password", json={"old_password": "alicepass", "new_password": "alicerocks"}),
    )
    assert payload["data"]["username"] == "alice"
    assert_ok(login(client, "alice", "alicerocks"))


def test_delete_user_requires_cookie_session(client, auth_headers, settings):
    seed_user(settings, "alice", "alicepass")
    # Bearer is not enough: DELETE /api/auth/user demands a cookie session. / Bearer không đủ; route này bắt buộc cookie.
    assert_fail(client.delete("/api/auth/user", headers=auth_headers), 401)


def test_delete_user_via_session(client, settings):
    seed_user(settings, "alice", "alicepass")
    login(client, "alice", "alicepass")
    payload = assert_ok(client.delete("/api/auth/user"))
    assert payload["data"]["deleted"] is True
    assert_fail(login(client, "alice", "alicepass"), 401)


def test_rate_limit_locks_ip_after_10_failures(client, settings):
    seed_user(settings, "alice", "goodpass")
    for _ in range(10):
        assert_fail(login(client, "alice", "wrongpass"), 401)
    # 11th attempt from the same IP is rejected before any verification. / Lần thứ 11 bị chặn trước khi kiểm tra.
    locked = login(client, "alice", "goodpass")
    assert_fail(locked, 429)
