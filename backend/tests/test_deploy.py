"""Production deployment support: DB URL normalization, production demo seed, token cleanup."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker
from app.core.config import Settings, normalize_database_url
from app.models import RefreshToken, User
from app.seed import ensure_seed_allowed
from app.services.auth import purge_expired_refresh_tokens
from tests.conftest import TEST_JWT_SECRET


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "production",
        "database_url": "postgres://u:p@h:5432/d",
        "jwt_secret": TEST_JWT_SECRET,
        "trusted_proxy_hops": 1,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+asyncpg://u:p@h:5432/d"),
        ("postgresql+asyncpg://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
    ],
)
def test_database_url_is_normalized_to_asyncpg(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected
    assert _settings(database_url=raw).database_url == expected


def test_empty_database_url_still_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(database_url="")


def test_production_seed_refused_by_default() -> None:
    with pytest.raises(SystemExit):
        ensure_seed_allowed(_settings())


def test_production_seed_needs_explicit_password() -> None:
    with pytest.raises(SystemExit):
        ensure_seed_allowed(_settings(seed_demo=True))
    with pytest.raises(SystemExit):
        ensure_seed_allowed(_settings(seed_demo=True, seed_password="short"))


def test_production_seed_allowed_with_flag_and_password() -> None:
    ensure_seed_allowed(_settings(seed_demo=True, seed_password="a-long-demo-password"))


def test_seed_allowed_outside_production() -> None:
    ensure_seed_allowed(_settings(app_env="development"))


async def test_purge_deletes_only_expired_refresh_tokens_and_is_idempotent(
    db_session: AsyncSession, client_a: User
) -> None:
    now = datetime.now(UTC)
    family = uuid.uuid4()

    def token(jti: str, expires_at: datetime) -> RefreshToken:
        return RefreshToken(
            jti=jti,
            family_id=family,
            user_id=client_a.id,
            family_started_at=now - timedelta(days=10),
            expires_at=expires_at,
        )

    db_session.add_all(
        [
            token("expired-1", now - timedelta(seconds=1)),
            token("expired-2", now - timedelta(days=3)),
            token("active", now + timedelta(days=1)),
        ]
    )
    await db_session.flush()

    assert await purge_expired_refresh_tokens(db_session, now) == 2
    assert await purge_expired_refresh_tokens(db_session, now) == 0
    left = (await db_session.scalars(select(RefreshToken.jti))).all()
    assert left == ["active"]


def test_purge_task_is_scheduled() -> None:
    schedule = worker.celery_app.conf.beat_schedule
    assert schedule["purge-expired-refresh-tokens"]["task"] == "auth.purge_expired_refresh_tokens"
    assert "auth.purge_expired_refresh_tokens" in worker.celery_app.tasks
