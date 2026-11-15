"""Shared fixtures: tmp settings tree, fake subprocess, fake httpx. / Fixture dùng chung."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from hermes_mgmt import deps, systemd_ctl  # noqa: E402
from hermes_mgmt.routes import codex  # noqa: E402
from hermes_mgmt.config import Settings, get_settings  # noqa: E402
from hermes_mgmt.env_file import set_env_value  # noqa: E402
from hermes_mgmt.main import create_app  # noqa: E402
from hermes_mgmt.systemd_ctl import CommandResult  # noqa: E402

API_KEY = "test-api-key"
SESSION_SECRET = "test-session-secret"
AUTH_TOKEN = "authtok123456"

PROVIDERS = (
    "anthropic",
    "openai",
    "google",
    "xai",
    "deepseek",
    "groq",
    "mistral",
    "together",
    "nous-portal",
    "openrouter",
    "huggingface",
    "kimi",
    "mimo",
    "minimax",
    "zai",
)
CHANNELS = ("telegram", "discord", "slack", "signal", "whatsapp", "email")
RULE_GROUPS = (
    "a-identity",
    "b-account-safety",
    "c-anti-spam-content",
    "d-security-privacy",
    "e-marketing-sales",
    "f-conversation-quality",
    "g-tools-actions",
    "h-operations-escalation",
)

CHANNEL_REQUIRED = {
    "telegram": ["token", "chat_id"],
    "discord": ["bot_token"],
    "slack": ["bot_token", "app_token"],
    "signal": ["account"],
    "whatsapp": ["token", "phone_id"],
    "email": ["smtp_host", "address"],
}


# --- Fake subprocess runner --------------------------------------------------


class FakeRunner:
    """Records argv and returns canned CommandResults. / Ghi argv và trả kết quả giả."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._results: dict[tuple[str, ...], CommandResult] = {}
        self.default = CommandResult(0, "ok", "")

    def set_result(
        self,
        *prefix: str,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        self._results[prefix] = CommandResult(exit_code, stdout, stderr)

    async def __call__(self, *argv: str, timeout: float = 60.0, cwd: str | None = None) -> CommandResult:
        self.calls.append(tuple(argv))
        best: tuple[int, CommandResult] | None = None
        for key, result in self._results.items():
            if argv[: len(key)] == key and (best is None or len(key) > best[0]):
                best = (len(key), result)
        return best[1] if best else self.default

    def called_with(self, *prefix: str) -> bool:
        return any(call[: len(prefix)] == prefix for call in self.calls)


@pytest.fixture()
def runner(monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    fake = FakeRunner()
    monkeypatch.setattr(systemd_ctl, "run_command", fake)
    return fake


@pytest.fixture(autouse=True)
def forbid_real_subprocess(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail loudly if any code path tries to spawn a real process. / Báo lỗi nếu có nơi nào chạy tiến trình thật."""

    async def _blocked(*argv: str, **kwargs: Any) -> CommandResult:
        raise AssertionError(f"real subprocess attempted: {argv}")

    monkeypatch.setattr(systemd_ctl, "_spawn", _blocked)
    yield


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    deps.reset_limiter()
    codex.reset_state()
    yield
    deps.reset_limiter()
    codex.reset_state()


# --- Fake httpx --------------------------------------------------------------


class FakeHttpxRouter:
    """URL -> canned httpx.Response (or exception) dispatcher. / Điều phối URL -> phản hồi giả."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Any] = {}
        self.calls: list[tuple[str, str]] = []

    def add(self, method: str, path: str, response: Any) -> None:
        self.routes[(method.upper(), path)] = response

    def resolve(self, method: str, url: str) -> Any:
        from urllib.parse import urlsplit

        path = urlsplit(url).path
        self.calls.append((method.upper(), path))
        key = (method.upper(), path)
        if key not in self.routes:
            raise httpx.ConnectError(f"connection refused: {url}")
        value = self.routes[key]
        if isinstance(value, Exception):
            raise value
        return value


class FakeAsyncClient:
    def __init__(self, router: FakeHttpxRouter, base_url: str = "", **kwargs: Any) -> None:
        self._router = router
        self.base_url = base_url

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def _full(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return self.base_url.rstrip("/") + "/" + url.lstrip("/")

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return self._router.resolve(method, self._full(url))

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)


@pytest.fixture()
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> FakeHttpxRouter:
    router = FakeHttpxRouter()

    def _factory(base_url: str = "", **kwargs: Any) -> FakeAsyncClient:
        return FakeAsyncClient(router, base_url=base_url)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return router


# --- Settings tree -----------------------------------------------------------


@pytest.fixture()
def settings_tree(tmp_path: Path) -> dict[str, Path]:
    """Build a full tmp layout: .env, templates, roles, hermes_home, logs. / Dựng cây thư mục tạm."""
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    templates = tmp_path / "templates"
    (templates / "channels").mkdir(parents=True)
    roles_config = tmp_path / "roles_config"
    (roles_config / "rules").mkdir(parents=True)
    (roles_config / "roles").mkdir(parents=True)
    log_dir = tmp_path / "var_log"
    log_dir.mkdir()
    (log_dir / "caddy").mkdir()
    openviking_dir = tmp_path / "openviking"
    openviking_home = tmp_path / "openviking_home"
    openviking_home.mkdir()
    hermes_src = tmp_path / "hermes_src"
    hermes_src.mkdir()
    mgmt_dir = tmp_path / "mgmt"
    mgmt_dir.mkdir()

    env_file = tmp_path / "hermes.env"
    env_file.write_text(
        "\n".join(
            [
                "DOMAIN=test.example.com",
                f"HERMES_MGMT_API_KEY={API_KEY}",
                f"HERMES_MGMT_SESSION_SECRET={SESSION_SECRET}",
                f"HERMES_AUTH_TOKEN={AUTH_TOKEN}",
                "HERMES_DROPLET_IP=203.0.113.10",
                "ZALO_PERSONAL_OWNER_UID=",
                "OPENAI_API_KEY=sk-test-1234567890",
                "",
            ]
        ),
        encoding="utf-8",
    )

    for provider in PROVIDERS:
        (templates / f"{provider}.json").write_text(
            json.dumps(
                {
                    "id": provider,
                    "label_vi": f"{provider} VI",
                    "label_en": f"{provider} EN",
                    "base_url": f"https://api.{provider}.example",
                    "api_key_env": provider.upper().replace("-", "_") + "_API_KEY",
                    "models": ["model-a", "model-b"],
                    "website": f"https://{provider}.example",
                    "notes_vi": "ghi chu",
                    "notes_en": "notes",
                }
            ),
            encoding="utf-8",
        )
    for channel in CHANNELS:
        (templates / "channels" / f"{channel}.json").write_text(
            json.dumps(
                {
                    "id": channel,
                    "label_vi": f"{channel} VI",
                    "label_en": f"{channel} EN",
                    "required_fields": CHANNEL_REQUIRED[channel],
                    "optional_fields": [],
                    "setup_vi": "huong dan",
                    "setup_en": "guide",
                }
            ),
            encoding="utf-8",
        )
    for group in RULE_GROUPS:
        (roles_config / "rules" / f"{group}.md").write_text(
            f"# Rule {group}\n\nNoi dung quy tac {group}.\n",
            encoding="utf-8",
        )
    (roles_config / "roles" / "cskh.yaml").write_text(
        "\n".join(
            [
                "id: cskh",
                'label_vi: "CSKH"',
                'label_en: "Support"',
                'description_vi: "Ho tro khach hang"',
                'description_en: "Customer support"',
                'emoji: "🎧"',
                'tone: "friendly"',
                "persona_vi: |",
                "  Ban la nhan vien CSKH.",
                "persona_en: |",
                "  You are support staff.",
                "rules: [a-identity, b-account-safety]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (roles_config / "roles" / "sales.yaml").write_text(
        "\n".join(
            [
                "id: sales",
                'label_vi: "Sales"',
                'label_en: "Sales"',
                'description_vi: "Ban hang"',
                'description_en: "Sales"',
                'emoji: "💰"',
                'tone: "persuasive"',
                "persona_vi: |",
                "  Ban la nhan vien ban hang.",
                "persona_en: |",
                "  You are sales staff.",
                "rules: [e-marketing-sales]",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "root": tmp_path,
        "env_file": env_file,
        "hermes_home": hermes_home,
        "templates": templates,
        "roles_config": roles_config,
        "log_dir": log_dir,
        "openviking_dir": openviking_dir,
        "openviking_home": openviking_home,
        "hermes_src": hermes_src,
        "mgmt_dir": mgmt_dir,
    }


@pytest.fixture()
def settings(settings_tree: dict[str, Path]) -> Settings:
    return Settings(
        hermes_mgmt_api_key=API_KEY,
        hermes_mgmt_session_secret=SESSION_SECRET,
        hermes_auth_token=AUTH_TOKEN,
        mgmt_env_file=settings_tree["env_file"],
        hermes_home=settings_tree["hermes_home"],
        templates_dir=settings_tree["templates"],
        roles_config_dir=settings_tree["roles_config"],
        log_dir=settings_tree["log_dir"],
        openviking_dir=settings_tree["openviking_dir"],
        openviking_home=settings_tree["openviking_home"],
        hermes_src_dir=settings_tree["hermes_src"],
        mgmt_dir=settings_tree["mgmt_dir"],
        install_dir=settings_tree["root"] / "install",
        cors_origins=["http://localhost.test"],
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}"}


# --- Assertion helpers -------------------------------------------------------


def assert_ok(response: httpx.Response, status_code: int = 200) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert payload["ok"] is True, payload
    assert payload["error"] is None, payload
    assert "data" in payload
    return payload


def assert_fail(response: httpx.Response, status_code: int | None = None) -> dict[str, Any]:
    if status_code is not None:
        assert response.status_code == status_code, response.text
    else:
        assert response.status_code >= 400, response.text
    payload = response.json()
    assert payload["ok"] is False, payload
    assert payload["data"] is None, payload
    assert payload["error"], payload
    return payload


def seed_user(settings: Settings, username: str, password: str) -> None:
    from hermes_mgmt.auth import UserStore

    UserStore(settings).add_user(username, password)


def login(client: TestClient, username: str, password: str) -> httpx.Response:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def write_env(settings: Settings, key: str, value: str) -> None:
    set_env_value(settings.mgmt_env_file, key, value)
