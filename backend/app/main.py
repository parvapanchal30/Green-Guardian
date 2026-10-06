from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.modules.identity.router import router as identity_router
from app.modules.weather.router import router as weather_router
from app.modules.workspaces.router import router as workspaces_router

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="GreenGuardian API", version="0.1.0", docs_url="/docs", openapi_url="/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    for r in (identity_router, workspaces_router, weather_router):
        app.include_router(r, prefix=API_PREFIX)

    @app.get("/healthz", tags=["system"])
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["system"])
    def readyz():
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}

    return app


# Run with:  uvicorn app.main:create_app --factory
