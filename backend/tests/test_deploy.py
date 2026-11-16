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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Supabase session pooler, as copied from its dashboard with libpq's sslmode.
        (
            "postgresql://postgres.ref:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
            "?sslmode=require",
            "postgresql+asyncpg://postgres.ref:pw@aws-0-eu-central-1.pooler.supabase.com:5432/"
            "postgres?ssl=require",
        ),
        ("postgresql://u:p@h/d?ssl=require", "postgresql+asyncpg://u:p@h/d?ssl=require"),
        # An explicit asyncpg `ssl` wins; the libpq duplicate is dropped.
        (
            "postgresql://u:p@h/d?sslmode=disable&ssl=require&application_name=api",
            "postgresql+asyncpg://u:p@h/d?ssl=require&application_name=api",
        ),
    ],
)
def test_sslmode_is_mapped_to_asyncpg_ssl(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected
    assert "sslmode" not in _settings(database_url=raw).database_url


@pytest.mark.parametrize("field", ["metrics_token", "logfire_token", "anthropic_api_key"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_optional_secret_counts_as_unset(field: str, blank: str) -> None:
    # A blank METRICS_TOKEN must not enable /metrics behind an empty bearer token.
    assert getattr(_settings(**{field: blank}), field) is None


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


class _FakeBeat:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def test_beat_thread_starts_once_and_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[_FakeBeat, dict[str, object]]] = []

    def fake_embedded(app: object, **kwargs: object) -> _FakeBeat:
        beat = _FakeBeat()
        created.append((beat, kwargs))
        return beat

    monkeypatch.setattr(worker, "EmbeddedService", fake_embedded)
    monkeypatch.setattr(worker, "_beat_service", None)

    monkeypatch.delenv("BEAT_IN_THREAD", raising=False)
    worker._start_beat_thread()
    assert created == []  # off by default: separate workers must not all run beat

    monkeypatch.setenv("BEAT_IN_THREAD", "1")
    worker._start_beat_thread()
    worker._start_beat_thread()  # a second worker_ready must not start a second scheduler
    assert len(created) == 1
    beat, kwargs = created[0]
    assert kwargs["thread"] is True  # a thread, not a forked process (512 MB budget)
    assert beat.started == 1

    worker._stop_beat_thread()
    assert beat.stopped == 1
