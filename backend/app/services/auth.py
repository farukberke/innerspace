import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    TokenError,
    TokenType,
    create_token,
    decode_token_with_jti,
    verify_password,
)
from app.models import RefreshToken, User
from app.services import audit
from app.services.errors import InvalidCredentialsError


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def issue_tokens(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    family_started_at: datetime | None = None,
) -> tuple[str, str]:
    """Returns (access, refresh) and records the refresh token's `jti`. Without a family a new
    session starts; a refresh continues its family, never beyond the absolute session limit."""
    now = datetime.now(UTC)
    started = family_started_at or now
    expires_at = min(
        now + timedelta(days=settings.refresh_token_days),
        started + timedelta(days=settings.session_max_days),
    )
    jti = uuid.uuid4().hex
    session.add(
        RefreshToken(
            jti=jti,
            family_id=family_id or uuid.uuid4(),
            user_id=user.id,
            family_started_at=started,
            expires_at=expires_at,
        )
    )
    await session.flush()
    return (
        create_token(settings, user.id, TokenType.ACCESS, now=now),
        create_token(settings, user.id, TokenType.REFRESH, now=now, expires_at=expires_at, jti=jti),
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
    tokens = await issue_tokens(session, settings, user)
    await session.commit()
    return tokens


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def _load_token(
    session: AsyncSession, settings: Settings, refresh_token: str
) -> RefreshToken | None:
    try:
        user_id, jti = decode_token_with_jti(settings, refresh_token, TokenType.REFRESH)
    except TokenError:
        return None
    return await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.jti == jti, RefreshToken.user_id == user_id)
        .with_for_update()
    )


async def refresh(session: AsyncSession, settings: Settings, refresh_token: str) -> tuple[str, str]:
    """Rotation: the presented token is consumed and a new pair issued. Presenting a consumed
    token again means it leaked, so the whole family is revoked."""
    record = await _load_token(session, settings, refresh_token)
    if record is None:
        raise InvalidCredentialsError
    user = await session.get(User, record.user_id)
    if user is None:
        raise InvalidCredentialsError
    now = datetime.now(UTC)
    if record.used_at is not None and record.revoked_at is None:
        await _revoke_family(session, record.family_id)
        await audit.record(
            session,
            "auth.refresh_reuse_detected",
            organization_id=user.organization_id,
            actor_id=user.id,
        )
        await session.commit()
        raise InvalidCredentialsError
    if (
        record.revoked_at is not None
        or record.used_at is not None
        or record.expires_at <= now
        or record.family_started_at + timedelta(days=settings.session_max_days) <= now
        or not user.is_active
    ):
        raise InvalidCredentialsError
    record.used_at = now
    tokens = await issue_tokens(
        session,
        settings,
        user,
        family_id=record.family_id,
        family_started_at=record.family_started_at,
    )
    await audit.record(
        session, "auth.refresh", organization_id=user.organization_id, actor_id=user.id
    )
    await session.commit()
    return tokens


async def logout(session: AsyncSession, settings: Settings, refresh_token: str) -> None:
    """Revokes the token's whole family. Idempotent; an unknown or invalid token is a no-op."""
    record = await _load_token(session, settings, refresh_token)
    if record is None:
        return
    await _revoke_family(session, record.family_id)
    user = await session.get(User, record.user_id)
    await audit.record(
        session,
        "auth.logout",
        organization_id=user.organization_id if user else None,
        actor_id=record.user_id,
    )
    await session.commit()
