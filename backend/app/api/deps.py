from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import session_scope
from app.models import User, UserRole


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(request.app.state.sessionmaker):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------------------
# TEMPORARY (Phase 1) — NO AUTHENTICATION.
# Every request acts as the seeded user named by DEV_USER_EMAIL. Disabled in production.
# Phase 2 replaces this with JWT authentication; nothing else should depend on how the
# current user is obtained.
# ---------------------------------------------------------------------------------------
async def get_current_user(session: SessionDep, settings: SettingsDep) -> User:
    if settings.is_production or not settings.dev_user_email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await session.scalar(select(User).where(User.email == settings.dev_user_email))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_client(user: CurrentUser) -> User:
    """Entries belong to clients; clinicians and admins never access them directly."""
    if user.role != UserRole.CLIENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only clients can access entries")
    return user


CurrentClient = Annotated[User, Depends(get_current_client)]
