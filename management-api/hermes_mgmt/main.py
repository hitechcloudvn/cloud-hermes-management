"""FastAPI app factory: CORS, middleware, router mount. / Factory app FastAPI: CORS, middleware, gắn router."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import Settings, get_settings
from .deps import require_auth
from .routes import (
    auth_routes,
    channels,
    cli_routes,
    codex,
    config_routes,
    control,
    cron_routes,
    env_routes,
    logs,
    openviking,
    roles,
    status,
    zalo,
)

PROTECTED_ROUTERS = (
    status.router,
    control.router,
    config_routes.router,
    channels.router,
    cron_routes.router,
    logs.router,
    env_routes.router,
    cli_routes.router,
    zalo.router,
    openviking.router,
    codex.router,
    roles.router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app; tests pass a settings instance. / Dựng app FastAPI; test truyền settings."""
    app = FastAPI(
        title="Hermes Management API",
        version=__version__,
        description="Management REST API for hermes-cloud-server / API quản trị cho hermes-cloud-server",
    )
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings

    cfg = settings if settings is not None else get_settings()
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Keep the {ok,data,error} envelope for HTTP errors. / Giữ phong bì {ok,data,error} cho lỗi HTTP.
        detail = exc.detail
        error = detail if isinstance(detail, str) else str(detail)
        return JSONResponse(status_code=exc.status_code, content={"ok": False, "data": None, "error": error})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, object]:
        """Liveness probe (no auth). / Kiểm tra sống (không cần auth)."""
        return {"ok": True, "version": __version__}

    for router in PROTECTED_ROUTERS:
        app.include_router(router, dependencies=[Depends(require_auth)])
    # auth_routes manages its own public/protected split. / auth_routes tự phân loại route công khai.
    app.include_router(auth_routes.router)
    return app


app = create_app()
