"""Settings for the management API (pydantic-settings). / Cấu hình API quản trị."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All paths and secrets flow through this object. / Mọi đường dẫn và bí mật đi qua đây."""

    model_config = SettingsConfigDict(
        populate_by_name=True,
        extra="ignore",
        case_sensitive=True,
    )

    # --- Secrets (loaded from /opt/hermes/.env via systemd EnvironmentFile) ---
    hermes_mgmt_api_key: str = Field(
        default="", validation_alias=AliasChoices("HERMES_MGMT_API_KEY", "hermes_mgmt_api_key")
    )
    hermes_mgmt_session_secret: str = Field(
        default="dev-session-secret",
        validation_alias=AliasChoices("HERMES_MGMT_SESSION_SECRET", "hermes_mgmt_session_secret"),
    )
    hermes_auth_token: str = Field(
        default="", validation_alias=AliasChoices("HERMES_AUTH_TOKEN", "hermes_auth_token")
    )

    # --- Ports / network ---
    port: int = Field(default=9997, validation_alias=AliasChoices("HERMES_MGMT_PORT", "port"))
    cors_origins: list[str] = Field(default_factory=list)

    # --- Paths ---
    mgmt_env_file: Path = Path("/opt/hermes/.env")
    install_dir: Path = Field(
        default=Path("/opt/hermes"),
        validation_alias=AliasChoices("HERMES_INSTALL_DIR", "install_dir"),
    )
    hermes_src_dir: Path = Path("/opt/hermes/hermes-agent")
    mgmt_dir: Path = Path("/opt/hermes-mgmt")
    hermes_home: Path = Path("/root/.hermes")
    templates_dir: Path = Field(
        default=Path("/etc/hermes/config"),
        validation_alias=AliasChoices("HERMES_TEMPLATES_DIR", "templates_dir"),
    )
    roles_config_dir: Path = Path("/opt/hermes-mgmt/config")
    log_dir: Path = Path("/var/log")
    hermes_bin: str = "hermes"

    # --- Zalo sidecar ---
    zalo_sidecar_url: str = "http://127.0.0.1:3838"

    # --- OpenViking memory backend ---
    openviking_dir: Path = Path("/opt/hermes-openviking")
    openviking_home: Path = Path("/root/.openviking")
    openviking_endpoint: str = "http://127.0.0.1:1933"
    openviking_service: str = "hermes-openviking.service"
    openviking_install_script: Path = Path("/opt/hermes/scripts/install-openviking.sh")
    openviking_uninstall_script: Path = Path("/opt/hermes/scripts/uninstall-openviking.sh")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Accept a comma-separated string from the environment too. / Chấp nhận chuỗi phân tách bằng dấu phẩy.
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def users_file(self) -> Path:
        return self.hermes_home / "mgmt_users.json"

    @property
    def roles_dir_custom(self) -> Path:
        return self.hermes_home / "roles"

    @property
    def persona_file(self) -> Path:
        return self.hermes_home / "persona.md"

    @property
    def active_role_file(self) -> Path:
        return self.hermes_home / "active_role.json"


def get_settings() -> Settings:
    """FastAPI dependency returning process settings. / Dependency FastAPI trả về cấu hình."""
    return Settings()
