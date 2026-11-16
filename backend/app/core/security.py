"""Password hashing, JWT creation, verification and opaque invitation tokens."""

import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

JWT_ALGORITHM = "HS256"  # fixed on purpose: never taken from the token header
_hasher = PasswordHasher()
# Verified against when the user does not exist, so login timing does not reveal accounts.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    pass


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish work whether or not a hash exists."""

    def _verify() -> bool:
        try:
            return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
        except (VerificationError, InvalidHashError):
            return False

    return await asyncio.to_thread(_verify)


def create_token(
    settings: Settings, user_id: uuid.UUID, token_type: TokenType, *, now: datetime | None = None
) -> str:
    now = now or datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == TokenType.ACCESS
        else timedelta(days=settings.refresh_token_days)
    )
    claims = {
        "sub": str(user_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_token(settings: Settings, token: str, expected: TokenType) -> uuid.UUID:
    """Returns the user id, or raises TokenError for any invalid/expired/wrong-type token."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
        if claims["type"] != expected.value:
            raise TokenError("wrong token type")
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise TokenError("invalid token") from exc


def new_invitation_token() -> tuple[str, str]:
    """Returns (plaintext token, sha256 hash). Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_invitation_token(token)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
