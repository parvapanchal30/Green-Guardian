"""Pure-ASGI middleware that establishes the request context and writes one access-log line per request."""

from __future__ import annotations

import json
import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .request_context import (
    REQUEST_ID_HEADER,
    accept_or_generate,
    client_ip_from_scope,
    reset_context,
    set_context,
)

log = structlog.get_logger("access")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, trusted_proxy_count: int = 0) -> None:
        self.app = app
        self.trusted_proxy_count = trusted_proxy_count

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k: v for k, v in scope.get("headers", [])}
        incoming = headers.get(REQUEST_ID_HEADER.encode())
        request_id = accept_or_generate(incoming.decode("latin-1") if incoming else None)
        ip = client_ip_from_scope(scope, self.trusted_proxy_count)
        agent = headers.get(b"user-agent")
        tokens = set_context(request_id, ip, agent.decode("latin-1") if agent else None)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_holder = {"status": 500, "started": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                hdrs = [(k, v) for k, v in message.get("headers", []) if k.lower() != REQUEST_ID_HEADER.encode()]
                hdrs.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": hdrs}
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_id)
            except Exception as exc:
                # Handled here (not by Starlette's outermost layer) so the request context is still set: the log line,
                # the response header and the body all carry the same ID. Internals never reach the client.
                log.error("unhandled_exception", error_type=type(exc).__name__, exc_info=exc)
                if status_holder["started"]:
                    raise
                body = json.dumps(
                    {
                        "type": "urn:greenguardian:problem:internal_error",
                        "title": "internal error",
                        "status": 500,
                        "code": "internal_error",
                        "detail": "Something went wrong on our side. Quote the request ID if you contact support.",
                        "instance": scope.get("path"),
                        "request_id": request_id,
                    }
                ).encode()
                await send_with_id(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/problem+json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send_with_id({"type": "http.response.body", "body": body})
        finally:
            log.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_holder["status"],
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                client_ip=ip,
            )
            structlog.contextvars.unbind_contextvars("request_id")
            reset_context(tokens)
