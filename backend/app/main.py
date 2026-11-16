from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin,
    ai,
    appointments,
    auth,
    entries,
    health,
    invitations,
    metrics,
    plans,
    summaries,
)
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import build_rate_limiter
from app.core.tracing import configure_tracing
from app.services.errors import RateLimitedError, RateLimiterUnavailableError

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.sessionmaker = create_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()
            await app.state.rate_limiter.close()

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="InnerSpace API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    app.state.rate_limiter = build_rate_limiter(settings)

    @app.exception_handler(RateLimitedError)
    async def _rate_limited(_request: Request, exc: RateLimitedError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Too many requests", "error_code": "rate_limited"},
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(RateLimiterUnavailableError)
    async def _limiter_unavailable(
        _request: Request, exc: RateLimiterUnavailableError
    ) -> JSONResponse:
        return JSONResponse(
            {"detail": "Service temporarily unavailable", "error_code": "limiter_unavailable"},
            status_code=503,
            headers={"Retry-After": str(exc.retry_after)},
        )

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
            expose_headers=["Retry-After", "X-Request-ID"],
        )
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(invitations.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(entries.router, prefix=API_PREFIX)
    app.include_router(summaries.router, prefix=API_PREFIX)
    app.include_router(ai.router, prefix=API_PREFIX)
    app.include_router(appointments.router, prefix=API_PREFIX)
    app.include_router(plans.router, prefix=API_PREFIX)
    return app
