"""Audit of authorization denials (HTTP 403).

Every `Forbidden` raised anywhere (the role dependencies and the services) passes through one exception handler, which
records an `access.denied` event and then returns the normal problem response. Design rules:

  * Best-effort: nothing in here may change the response. Any failure is logged and swallowed.
  * No recursion: a re-entrancy guard stops the recorder from recording its own failures.
  * No flooding: the same actor, route and reason is recorded at most once per `audit_denied_dedupe_s` per process.
  * Minimal data: method, route TEMPLATE (never ids or query strings), the reason code and the (non-sensitive) message.
    Request bodies, headers and tokens are never read.
  * Context: request ID, client address and user agent come from the request context; actor and workspace from the
    identity noted when authentication resolved (absent for failures before that point).
Only 403s are recorded here: a non-member probing a workspace gets 404 by design (existence is not revealed), and 401s
are unauthenticated noise.
"""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

import structlog
from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app.core.db import get_db
from app.core.errors import Forbidden, app_error_response
from app.core.request_context import current_identity

from . import service

log = structlog.get_logger()

_busy: ContextVar[bool] = ContextVar("audit_denied_busy", default=False)
_recent: dict[tuple, float] = {}
_MAX_REMEMBERED = 2000
_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}")


def route_template(request: Request) -> str:
    """The URL with its path-parameter values replaced by their names, e.g. /api/v1/workspaces/{ws}/assets.
    (The matched route object stores a prefix-relative path, so the real path is templated instead.)"""
    path = request.url.path
    for name, value in (request.scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}")
    return _ID.sub("{id}", path)[:200]  # anything the matcher did not name (unmatched routes) is still masked


def _seen_recently(key: tuple, window_s: int, now: float) -> bool:
    if window_s <= 0:
        return False
    last = _recent.get(key)
    if last is not None and now - last < window_s:
        return True
    if len(_recent) >= _MAX_REMEMBERED:  # bounded memory: forget the oldest half
        for old in sorted(_recent, key=_recent.get)[: _MAX_REMEMBERED // 2]:  # type: ignore[arg-type]
            _recent.pop(old, None)
    _recent[key] = now
    return False


def reset_dedupe() -> None:
    """For tests."""
    _recent.clear()


def _record(app: FastAPI, method: str, route: str, exc: Forbidden) -> None:
    window = getattr(getattr(app.state, "settings", None), "audit_denied_dedupe_s", 60)
    ident = current_identity()
    actor, workspace = ident.get("actor_id"), ident.get("workspace_id")
    if _seen_recently((actor, workspace, method, route, exc.code), window, time.monotonic()):
        return
    session_factory = app.dependency_overrides.get(get_db, get_db)  # same session source the request used
    gen = session_factory()
    db = next(gen)
    try:
        service.record(
            db,
            action="access.denied",
            outcome="denied",
            workspace_id=workspace if isinstance(workspace, uuid.UUID) else None,
            actor_id=actor if isinstance(actor, uuid.UUID) else None,
            details={"reason": exc.code, "message": exc.detail, "method": method, "route": route},
        )
        db.commit()
    finally:
        gen.close()


def install(app: FastAPI) -> None:
    @app.exception_handler(Forbidden)
    async def _forbidden(request: Request, exc: Forbidden):
        if not _busy.get():
            token = _busy.set(True)
            try:
                await run_in_threadpool(_record, request.app, request.method, route_template(request), exc)
            except Exception as err:  # never let auditing change the answer
                log.error("access_denied_audit_failed", error_type=type(err).__name__, error=str(err)[:200])
            finally:
                _busy.reset(token)
        return app_error_response(request, exc)
