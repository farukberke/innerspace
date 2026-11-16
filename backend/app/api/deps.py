import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic_ai.models import Model
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import AiUnavailableError, build_model
from app.core.config import Settings
from app.core.db import session_scope
from app.core.ratelimit import RateLimiter, parse_limit
from app.core.security import TokenError, TokenType, decode_token
from app.models import User, UserRole


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.sessionmaker):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Authenticates the bearer access token (refresh tokens are rejected) and loads the user."""
    if credentials is None:
        raise _unauthorized()
    try:
        user_id = decode_token(settings, credentials.credentials, TokenType.ACCESS)
    except TokenError:
        raise _unauthorized() from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: the authenticated user must have exactly this role (else 403)."""

    async def _dependency(user: CurrentUser) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dependency


CurrentClient = Annotated[User, Depends(require_role(UserRole.CLIENT))]
CurrentClinician = Annotated[User, Depends(require_role(UserRole.CLINICIAN))]
CurrentOrgAdmin = Annotated[User, Depends(require_role(UserRole.ORG_ADMIN))]


def get_llm_model(settings: SettingsDep) -> Model:
    """The configured LLM. Without an API key every AI endpoint answers 503. Tests override
    this dependency, so they never reach a real provider."""
    try:
        return build_model(settings)
    except AiUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI features are not available"
        ) from None


LlmModelDep = Annotated[Model, Depends(get_llm_model)]


JobEnqueuer = Callable[[uuid.UUID], None]


def get_job_enqueuer() -> JobEnqueuer:
    """Hands a job id to the Celery queue. Tests override this dependency (no Redis needed)."""
    from app.worker import enqueue_summary_job  # noqa: PLC0415  (keeps Celery out of app import)

    return enqueue_summary_job


JobEnqueuerDep = Annotated[JobEnqueuer, Depends(get_job_enqueuer)]


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def client_ip(request: Request) -> str:
    """The peer address. Behind a proxy run uvicorn with --proxy-headers/--forwarded-allow-ips
    so this is the real client, never a spoofable header read by the app itself."""
    return request.client.host if request.client else "unknown"


def limit_per_ip(name: str) -> Callable[..., Awaitable[None]]:
    """Dependency factory: `rate_limit_<name>` per client IP."""

    async def _dependency(request: Request, limiter: RateLimiterDep, settings: SettingsDep) -> None:
        limit = parse_limit(getattr(settings, f"rate_limit_{name}"))
        await limiter.check(name, client_ip(request), limit)

    return _dependency


def limit_per_user(name: str) -> Callable[..., Awaitable[None]]:
    """Dependency factory: `rate_limit_<name>` per authenticated user."""

    async def _dependency(
        user: CurrentUser, limiter: RateLimiterDep, settings: SettingsDep
    ) -> None:
        limit = parse_limit(getattr(settings, f"rate_limit_{name}"))
        await limiter.check(name, str(user.id), limit)

    return _dependency
