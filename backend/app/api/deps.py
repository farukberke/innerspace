from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import session_scope
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
