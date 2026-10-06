"""The weather boundary (ADR-024): Agent -> WeatherContextProvider (port) <- adapter -> WeatherService -> WeatherProvider.

No test here touches the network.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import create_app
from app.modules.intelligence.ports import WeatherContext, WeatherContextProvider
from app.modules.weather import registry
from app.modules.weather.context import ForecastWeatherContext, summarize_forecast
from app.modules.weather.domain import Forecast, HourlyPoint, WeatherUnavailable
from app.modules.weather.service import WeatherService

APP = Path(__file__).resolve().parents[1] / "app"
NOW = datetime(2026, 10, 7, 6, 30, tzinfo=UTC)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module if node.level == 0 else None
            if base:
                out.add(base)
                out.update(f"{base}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def _py_files(sub: str):
    return [p for p in (APP / sub).rglob("*.py")]


def test_agent_and_domain_code_never_import_the_weather_package():
    offenders = {
        str(p.relative_to(APP)): sorted(i for i in _imports(p) if i.startswith("app.modules.weather"))
        for p in _py_files("modules/intelligence")
    }
    assert not {k: v for k, v in offenders.items() if v}, offenders


def test_only_the_registry_knows_concrete_providers():
    """Nothing outside the weather package, and nothing in the weather package except the registry, may import a
    concrete provider module (open_meteo / mock)."""
    concrete = ("app.modules.weather.open_meteo", "app.modules.weather.mock")
    offenders = []
    for p in APP.rglob("*.py"):
        rel = p.relative_to(APP).as_posix()
        if rel in {"modules/weather/registry.py", "modules/weather/open_meteo.py", "modules/weather/mock.py"}:
            continue
        for imp in _imports(p):
            if imp.startswith(concrete):
                offenders.append((rel, imp))
        # relative imports inside the weather package
        if rel.startswith("modules/weather/"):
            src = p.read_text(encoding="utf8")
            if "from .open_meteo" in src or "from .mock" in src:
                offenders.append((rel, "relative import of a concrete provider"))
    assert not offenders, offenders


def _code_without_docstrings(path: Path) -> str:
    """Source as the interpreter sees it: comments are gone and docstrings are removed, so prose cannot trigger a
    false positive (e.g. a docstring that draws the architecture diagram)."""
    tree = ast.parse(path.read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                if isinstance(body[0].value.value, str):
                    node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_open_meteo_specifics_are_confined_to_config_and_the_adapter():
    allowed = {
        "core/config.py",  # provider key + its endpoint setting
        "modules/weather/open_meteo.py",
        "modules/weather/registry.py",
        # provenance labels inside the weather package, e.g. `source: str  # "open_meteo" | "mock"`
        "modules/weather/domain.py",
        "modules/weather/service.py",
        "modules/weather/mock.py",
    }
    hits = {
        p.relative_to(APP).as_posix()
        for p in APP.rglob("*.py")
        if "open_meteo"
        in _code_without_docstrings(p).lower().replace("open-meteo", "open_meteo").replace("openmeteo", "open_meteo")
    }
    unexpected = hits - allowed
    assert not unexpected, f"Open-Meteo referenced in code outside the weather boundary: {unexpected}"


# ---------------------------------------------------------------- registry & substitution


def test_default_registry_has_open_meteo_and_mock():
    assert {"open_meteo", "mock"} <= set(registry.available_providers())


def test_unknown_provider_fails_fast_with_the_available_options(settings):
    bad = settings.model_copy(update={"weather_provider": "accuweather"})
    with pytest.raises(registry.UnknownWeatherProvider, match="open_meteo"):
        registry.build_provider(bad)
    with pytest.raises(registry.UnknownWeatherProvider):
        create_app(bad)  # misconfiguration is caught at startup, not at the first request


class FakeProvider:
    key = "fake"

    def __init__(self):
        self.calls = 0

    def forecast(self, latitude: float, longitude: float, days: int) -> Forecast:
        self.calls += 1
        start = NOW.replace(minute=0)
        pts = tuple(
            HourlyPoint(
                time=start + timedelta(hours=h),
                precipitation_mm=0.5,
                precipitation_probability_pct=30.0 + h,
                temperature_c=20.0,
                soil_moisture={"0_to_1cm": 0.25},
            )
            for h in range(48)
        )
        return Forecast(latitude, longitude, "UTC", self.key, "fake data", NOW, pts)


def test_a_new_provider_plugs_in_without_touching_agent_code(settings):
    fake = FakeProvider()
    registry.register_provider("fake", lambda s: fake)
    try:
        provider = registry.build_provider(settings.model_copy(update={"weather_provider": "fake"}))
        port: WeatherContextProvider = ForecastWeatherContext(WeatherService(provider, 60))
        ctx = port.context_for(19.2, 72.97, NOW)
        assert ctx is not None and ctx.source == "fake"
        assert ctx.rain_next_24h_mm == 12.0  # 24 hourly values of 0.5 mm
        assert ctx.max_rain_probability_pct == 30.0 + 23
        assert ctx.soil_moisture_top == 0.25 and ctx.temperature_c == 20.0
        assert fake.calls == 1
    finally:
        registry._FACTORIES.pop("fake", None)


# ---------------------------------------------------------------- adapter behaviour


def test_adapter_returns_none_instead_of_raising_when_the_provider_is_down():
    class Down:
        key = "down"

        def forecast(self, *a):
            raise WeatherUnavailable("provider exploded: secret-detail")

    assert ForecastWeatherContext(WeatherService(Down(), 1)).context_for(1, 1, NOW) is None


def test_context_is_none_when_forecast_does_not_cover_now():
    fc = FakeProvider().forecast(1, 1, 2)
    assert summarize_forecast(fc, NOW + timedelta(days=30)) is None


def test_unknown_values_stay_unknown_not_zero():
    pts = (HourlyPoint(time=NOW.replace(minute=0)),)
    ctx = summarize_forecast(Forecast(1, 1, "UTC", "x", "a", NOW, pts), NOW)
    assert isinstance(ctx, WeatherContext)
    assert ctx.rain_next_24h_mm is None and ctx.max_rain_probability_pct is None and ctx.soil_moisture_top is None


def test_naive_now_is_treated_as_utc():
    fc = FakeProvider().forecast(1, 1, 2)
    assert summarize_forecast(fc, NOW.replace(tzinfo=None)) is not None


def test_settings_accept_any_provider_key_string():
    # the key set is owned by the registry, not hard-coded in configuration
    assert Settings(weather_provider="somebody_else", _env_file=None).weather_provider == "somebody_else"
