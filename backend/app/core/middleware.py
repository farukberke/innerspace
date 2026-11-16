import logging
import os
import re
import time
import traceback
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.logging import request_id_var
from app.core.metrics import METRICS

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger("app.request")


def new_request_id(incoming: str | None = None) -> str:
    """Keeps a well-formed incoming ID (so a trace can span services), otherwise a fresh one."""
    return incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex


def _error_location(exc: BaseException) -> str:
    """Innermost frame as `file:line in function`: enough to find the bug, without the
    exception message (which could echo user content)."""
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return "unknown"
    last = frames[-1]
    return f"{os.path.basename(last.filename)}:{last.lineno} in {last.name}"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, logs one line per request, records metrics and hides unhandled
    error details (clients get an error_code and the request ID; logs get no content)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = new_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.error(
                    "unhandled_error",
                    extra={
                        "error_code": "internal_error",
                        "error_type": type(exc).__name__,
                        "location": _error_location(exc),
                    },
                )
                METRICS.observe_error("internal_error")
                response = JSONResponse(
                    {
                        "detail": "Internal server error",
                        "error_code": "internal_error",
                        "request_id": request_id,
                    },
                    status_code=500,
                )
            seconds = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", "unmatched")
            METRICS.observe_request(request.method, route, response.status_code, seconds)
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    # Path only: the query string may carry user-provided values.
                    "path": request.url.path,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(seconds * 1000, 2),
                },
            )
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            request_id_var.reset(token)
