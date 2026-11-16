import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import TokenError, TokenType, create_token, decode_token, verify_password
from app.models import User
from app.services import audit
from app.services.errors import InvalidCredentialsError


def normalize_email(email: str) -> str:
    return email.strip().lower()


def issue_tokens(settings: Settings, user_id: uuid.UUID) -> tuple[str, str]:
    return (
        create_token(settings, user_id, TokenType.ACCESS),
        create_token(settings, user_id, TokenType.REFRESH),
    )


async def authenticate(
    session: AsyncSession, settings: Settings, email: str, password: str
) -> tuple[str, str]:
    """Returns (access, refresh). Failures are audited (without the e-mail) and committed."""
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    valid = await verify_password(password, user.password_hash if user else None)
    if user is None or not valid or not user.is_active:
        await audit.record(
            session,
            "auth.login_failed",
            organization_id=user.organization_id if user else None,
            actor_id=user.id if user else None,
            detail={"known_account": user is not None},
        )
        await session.commit()
        raise InvalidCredentialsError
    await audit.record(
        session, "auth.login", organization_id=user.organization_id, actor_id=user.id
    )
    await session.commit()
    return issue_tokens(settings, user.id)


async def refresh(session: AsyncSession, settings: Settings, refresh_token: str) -> tuple[str, str]:
    try:
        user_id = decode_token(settings, refresh_token, TokenType.REFRESH)
    except TokenError:
        raise InvalidCredentialsError from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidCredentialsError
    return issue_tokens(settings, user.id)
