"""Background worker: scheduled agent runs and housekeeping. Same image as the API, different command.

    python -m app.worker                 # run until SIGTERM / SIGINT, then finish the current run and exit
    python -m app.worker --once          # one pass (cron-style deployments, smoke tests), then exit
    python -m app.worker --healthcheck   # exit 0 if the worker's heartbeat is recent (container health check)

State lives only in the database (run history), so the worker can be stopped, restarted or duplicated freely.
This module is a composition root: it is allowed to wire the weather service into the agent's port (ADR-024).
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.core.db import get_sessionmaker
from app.core.logging import configure_logging
from app.modules.intelligence import scheduler
from app.modules.intelligence.ports import WeatherContextProvider
from app.tools import housekeeping

log = structlog.get_logger()

HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT_FILE", Path(tempfile.gettempdir()) / "gg-worker.heartbeat"))


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def build_weather(settings: Settings) -> WeatherContextProvider | None:
    from app.modules.weather.context import ForecastWeatherContext
    from app.modules.weather.service import get_weather_service

    return ForecastWeatherContext(get_weather_service())


def beat() -> None:
    try:
        HEARTBEAT.write_text(str(time.time()))
    except OSError:  # a read-only filesystem must not stop the worker; the health check will say so
        log.warning("heartbeat_unwritable", path=str(HEARTBEAT))


def healthy(max_age_s: float) -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) <= max_age_s
    except (OSError, ValueError):
        return False


def run(stop: threading.Event, *, once: bool = False) -> None:
    settings = get_settings()
    weather = build_weather(settings)
    me = worker_id()
    next_housekeeping = 0.0
    log.info("worker_started", worker_id=me, poll_s=settings.worker_poll_interval_s)
    while not stop.is_set():
        beat()
        try:
            t = scheduler.tick(
                get_sessionmaker(),
                weather=weather,
                worker_id=me,
                stale_run_s=settings.agent_stale_run_s,
                should_stop=stop.is_set,
            )
            if t.due or t.reaped:
                log.info("worker_tick", **t.__dict__)
        except Exception:  # never die on a transient failure (database restart, network): try again next tick
            log.exception("worker_tick_failed")
        if time.monotonic() >= next_housekeeping and not stop.is_set():
            try:
                log.info("housekeeping_done", **housekeeping.run())
            except Exception:
                log.exception("housekeeping_failed")
            next_housekeeping = time.monotonic() + settings.housekeeping_interval_s
        if once:
            break
        stop.wait(settings.worker_poll_interval_s)
    log.info("worker_stopped", worker_id=me)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--healthcheck", action="store_true", help="exit 0 if the heartbeat is recent")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.healthcheck:
        return 0 if healthy(max(settings.worker_poll_interval_s * 3, 120)) else 1
    configure_logging(settings.log_level)
    stop = threading.Event()
    # SIGTERM is what container platforms send; SIGINT is Ctrl+C; SIGBREAK is the Windows equivalent of a terminate
    # request (Windows has no real SIGTERM delivery, so a development machine uses Ctrl+Break).
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if (sig := getattr(signal, name, None)) is not None:
            signal.signal(sig, lambda *_: stop.set())
    run(stop, once=args.once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
