from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette import status

from app.core.logging import get_logger


logger = get_logger(__name__)


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    if isinstance(rid, str) and rid:
        return rid
    return request.headers.get("X-Request-Id")


def _error_payload(*, request_id: str | None, code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": request_id,
        "error": {"code": code, "message": message},
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        rid = _request_id(request)

        code = "http_error"
        message = "Request failed"
        details: Any | None = None

        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code") or code)
            message = str(exc.detail.get("message") or message)
            details = exc.detail.get("details")
        elif isinstance(exc.detail, str):
            message = exc.detail
        else:
            details = exc.detail

        return ORJSONResponse(
            status_code=int(exc.status_code),
            content=_error_payload(request_id=rid, code=code, message=message, details=details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        rid = _request_id(request)
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                request_id=rid,
                code="validation_error",
                message="Request validation error",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = _request_id(request)
        logger.exception("unhandled_exception", request_id=rid)
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_payload(request_id=rid, code="internal_error", message="Internal server error"),
        )
