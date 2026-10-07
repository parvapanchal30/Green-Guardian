"""Typed domain errors mapped to RFC 7807 problem+json."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, detail: str = "", *, code: str | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.detail = detail or self.code
        if code:
            self.code = code
        self.extra = extra or {}


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


class Forbidden(AppError):
    status, code = 403, "forbidden"


class NotFound(AppError):
    status, code = 404, "not_found"


class Unprocessable(AppError):
    status, code = 422, "unprocessable"


class Conflict(AppError):
    status, code = 409, "conflict"


class CapabilityUnavailable(AppError):
    status, code = 501, "capability_unavailable"


class ProviderUnavailable(AppError):
    status, code = 503, "provider_unavailable"


def _problem(request: Request, status: int, code: str, detail: str, **extra) -> JSONResponse:
    body = {
        "type": f"urn:greenguardian:problem:{code}",
        "title": code.replace("_", " "),
        "status": status,
        "code": code,
        "detail": detail,
        "instance": request.url.path,
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        resp = _problem(request, exc.status, exc.code, exc.detail, **exc.extra)
        if headers:
            resp.headers.update(headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return _problem(request, 422, "validation_error", "Request validation failed", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return _problem(request, exc.status_code, "http_error", str(exc.detail))
