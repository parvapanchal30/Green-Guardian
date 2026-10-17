from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.modules.assets.router import router as assets_router
from app.modules.audit import denied as audit_denied
from app.modules.audit.router import router as audit_router
from app.modules.catalog.router import router as catalog_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.evidence.router import router as evidence_router
from app.modules.evidence.storage import UnknownStorageProvider, available_stores
from app.modules.identity.router import router as identity_router
from app.modules.intelligence.ports import WeatherContextProvider, get_weather_context_provider
from app.modules.intelligence.router import router as intelligence_router
from app.modules.issues.router import router as issues_router
from app.modules.locations.router import router as locations_router
from app.modules.map.router import router as map_router
from app.modules.observations.router import router as observations_router
from app.modules.tasks.router import router as tasks_router
from app.modules.weather.context import ForecastWeatherContext
from app.modules.weather.registry import UnknownWeatherProvider, available_providers
from app.modules.weather.router import router as weather_router
from app.modules.weather.service import WeatherService, get_weather_service
from app.modules.workspaces.router import router as workspaces_router

API_PREFIX = "/api/v1"


def validate_weather_provider(settings: Settings) -> None:
    if settings.weather_provider not in available_providers():
        raise UnknownWeatherProvider(
            f"WEATHER_PROVIDER={settings.weather_provider!r} is not registered; available: {available_providers()}"
        )


def validate_storage_provider(settings: Settings) -> None:
    if settings.storage_provider not in available_stores():
        raise UnknownStorageProvider(
            f"STORAGE_PROVIDER={settings.storage_provider!r} is not registered; available: {available_stores()}"
        )


def _weather_context(service: WeatherService = Depends(get_weather_service)) -> WeatherContextProvider:
    """Composition root: the agent asks for a WeatherContextProvider (its own port); we answer with the adapter over
    whichever weather service/provider is configured (tests override `get_weather_service`)."""
    return ForecastWeatherContext(service)


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
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    # Added last = outermost: every response (including CORS preflights and errors) carries the request ID.
    app.add_middleware(RequestContextMiddleware, trusted_proxy_count=settings.trusted_proxy_count)
    install_error_handlers(app)
    audit_denied.install(app)  # records 403s, then answers exactly as before
    app.state.settings = settings
    app.dependency_overrides[get_weather_context_provider] = _weather_context
    validate_weather_provider(settings)
    validate_storage_provider(settings)

    for r in (
        identity_router,
        workspaces_router,
        weather_router,
        locations_router,
        catalog_router,
        assets_router,
        observations_router,
        issues_router,
        tasks_router,
        intelligence_router,
        dashboard_router,
        map_router,
        evidence_router,
        audit_router,
    ):
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
