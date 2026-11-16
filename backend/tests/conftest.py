"""Test setup.

Tests run against a real PostgreSQL database: the `<DATABASE_URL db>_test` database on the
same server (created by docker compose). Migrations are applied once per run; every test
runs inside a transaction that is rolled back afterwards.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from alembic import command
from app.api.deps import get_current_user, get_session
from app.core.config import Settings, get_settings
from app.main import create_app
from app.models import Organization, User, UserRole

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(app_env="test", database_url=_test_database_url(), dev_user_email=None)


@pytest.fixture(scope="session")
def alembic_config(test_settings: Settings) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", test_settings.database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated_db(alembic_config: Config) -> Iterator[None]:
    # Full downgrade + upgrade also exercises the downgrade path of every migration.
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture(scope="session")
async def engine(test_settings: Settings, migrated_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(test_settings.database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


# --- Data factories --------------------------------------------------------------------


@pytest.fixture
def make_org(db_session: AsyncSession) -> Callable[[str], object]:
    async def _make(slug: str) -> Organization:
        org = Organization(slug=slug, name=f"{slug} (test)")
        db_session.add(org)
        await db_session.flush()
        return org

    return _make


@pytest.fixture
def make_user(db_session: AsyncSession) -> Callable[..., object]:
    async def _make(org: Organization, role: UserRole, name: str) -> User:
        user = User(
            organization_id=org.id,
            email=f"{name}@{org.slug}.test",
            display_name=name,
            role=role,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


@pytest.fixture
async def org_a(make_org) -> Organization:
    return await make_org("org-a")


@pytest.fixture
async def org_b(make_org) -> Organization:
    return await make_org("org-b")


@pytest.fixture
async def client_a(make_user, org_a) -> User:
    return await make_user(org_a, UserRole.CLIENT, "client-a")


# --- App / HTTP ------------------------------------------------------------------------


class ActingUser:
    """Which user the request is made as. Stands in for authentication until Phase 2."""

    def __init__(self) -> None:
        self.user: User | None = None


@pytest.fixture
def acting() -> ActingUser:
    return ActingUser()


@pytest.fixture
async def http(
    test_settings: Settings, db_session: AsyncSession, acting: ActingUser
) -> AsyncIterator[AsyncClient]:
    app = create_app(test_settings)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _current_user() -> User:
        assert acting.user is not None, "set `acting.user` before calling the API"
        return acting.user

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = _current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
