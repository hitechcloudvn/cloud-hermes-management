"""Pydantic v2 schemas for all endpoints + ApiResponse envelope. / Schema Pydantic v2 cho mọi endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi.responses import JSONResponse

# --- Response envelope -------------------------------------------------------


class ApiResponse(BaseModel):
    """Uniform response envelope. / Phong bì phản hồi thống nhất."""

    ok: bool
    data: Any | None = None
    error: str | None = None


def ok(data: Any = None, status_code: int = 200) -> JSONResponse:
    """Return a success envelope. / Trả về phong bì thành công."""
    return JSONResponse(status_code=status_code, content={"ok": True, "data": data, "error": None})


def fail(error: str, status_code: int = 400) -> JSONResponse:
    """Return a failure envelope. / Trả về phong bì thất bại."""
    return JSONResponse(status_code=status_code, content={"ok": False, "data": None, "error": error})


# --- Auth --------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


# --- Control -----------------------------------------------------------------


class ResetRequest(BaseModel):
    confirm: str


class DomainRequest(BaseModel):
    domain: str = Field(min_length=1)


# --- Config ------------------------------------------------------------------


class ProviderSetRequest(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)


class ApiKeyRequest(BaseModel):
    provider: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class TestKeyRequest(BaseModel):
    provider: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


# --- Channels ----------------------------------------------------------------


class ChannelPutRequest(BaseModel):
    """Provider-specific channel fields; required fields checked per channel. / Trường kênh theo nhà cung cấp."""

    model_config = ConfigDict(extra="allow")


# --- Cron --------------------------------------------------------------------


class CronCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    schedule: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    job_id: str | None = None
    description: str = ""


# --- Env ---------------------------------------------------------------------


class EnvPutRequest(BaseModel):
    value: str


# --- CLI ---------------------------------------------------------------------


class CliRequest(BaseModel):
    subcommand: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)


# --- Zalo --------------------------------------------------------------------


class ZaloSetOwnerRequest(BaseModel):
    phone: str | None = None
    uid: str | None = None

    @model_validator(mode="after")
    def _need_phone_or_uid(self) -> "ZaloSetOwnerRequest":
        if not self.phone and not self.uid:
            raise ValueError("either 'phone' or 'uid' is required")
        return self


# --- OpenViking --------------------------------------------------------------


class OpenVikingConfigRequest(BaseModel):
    api_key: str = Field(min_length=1)
    api_base: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    vlm_model: str = "gpt-4o-mini"
    provider: str = "openai"
    dimension: int = 1536


class OpenVikingTestKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)
    api_base: str = "https://api.openai.com/v1"


class OpenVikingUninstallRequest(BaseModel):
    purge: bool = False


# --- Codex -------------------------------------------------------------------


class CodexImportRequest(BaseModel):
    auth_json: str | dict[str, Any]


class CodexDisableRequest(BaseModel):
    to_provider: str | None = None


# --- Roles -------------------------------------------------------------------


class RoleCreateRequest(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    persona: str = Field(min_length=1)
    label: str = ""
    description: str = ""
    emoji: str = ""
    tone: str = ""
    rules: list[str] = Field(default_factory=list)
