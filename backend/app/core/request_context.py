"""Per-request context: correlation ID, client address, user agent.

Stored in `contextvars`, so any code running for a request (including synchronous handlers, which Starlette runs in a
threadpool with a copy of the context) can read it without being passed a Request: logging, error bodies, audit rows.

Safety rules:
  * An incoming X-Request-ID is accepted only if it matches a strict pattern; anything else is discarded and a fresh
    ID is generated (never echoed back), which blocks log injection and header reflection.
  * The client address is the socket peer unless TRUSTED_PROXY_COUNT > 0, in which case it is the Nth entry from the
    right of X-Forwarded-For (the last N proxies are trusted; anything further left is client-controlled).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

REQUEST_ID_HEADER = "x-request-id"
_VALID_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)
_user_agent: ContextVar[str | None] = ContextVar("user_agent", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def accept_or_generate(incoming: str | None) -> str:
    """The caller's ID if it is well-formed, otherwise a new one."""
    if incoming and _VALID_ID.match(incoming):
        return incoming
    return new_request_id()


def client_ip_from_scope(scope: Mapping[str, Any], trusted_proxy_count: int) -> str | None:
    peer = scope.get("client")
    peer_ip = peer[0] if peer else None
    if trusted_proxy_count <= 0:
        return peer_ip
    forwarded = ""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            forwarded = value.decode("latin-1")
            break
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    if len(hops) >= trusted_proxy_count:
        return hops[-trusted_proxy_count][:64]
    return peer_ip


def set_context(request_id: str, client_ip: str | None, user_agent: str | None):
    """Returns the tokens needed to reset the variables."""
    return (_request_id.set(request_id), _client_ip.set(client_ip), _user_agent.set((user_agent or "")[:300] or None))


def reset_context(tokens) -> None:
    _request_id.reset(tokens[0])
    _client_ip.reset(tokens[1])
    _user_agent.reset(tokens[2])


def current_request_id() -> str | None:
    return _request_id.get()


def current_client_ip() -> str | None:
    return _client_ip.get()


def current_user_agent() -> str | None:
    return _user_agent.get()
