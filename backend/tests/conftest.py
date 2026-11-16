"""Test setup.

Tests run against a real PostgreSQL database: the `<DATABASE_URL db>_test` database on the
same server (created by docker compose). Migrations are applied once per run; every test
runs inside a transaction that is rolled back afterwards.
"""

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic_ai import models
from pydantic_ai.models import Model
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from alembic import command
from app.api.deps import get_job_enqueuer, get_llm_model, get_session
from app.core.config import Settings, get_settings
from app.core.security import TokenType, create_token, hash_password
from app.main import create_app
from app.models import Organization, User, UserRole

TEST_JWT_SECRET = "test-secret-test-secret-test-secret-0123456789"  # noqa: S105
TEST_PASSWORD = "correct-horse-battery"  # noqa: S105

# Safety net: any attempt to call a real model provider raises instead of sending a request.
models.ALLOW_MODEL_REQUESTS = False

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_database_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url=_test_database_url(),
        jwt_secret=TEST_JWT_SECRET,
        anthropic_api_key=None,  # tests must never be able to reach a real provider
        rate_limit_backend="memory",  # no Redis in tests
        logfire_token=None,
    )


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
async def password_hash() -> str:
    return await hash_password(TEST_PASSWORD)


@pytest.fixture
def make_user(db_session: AsyncSession, password_hash: str) -> Callable[..., object]:
    async def _make(org: Organization, role: UserRole, name: str) -> User:
        user = User(
            organization_id=org.id,
            email=f"{name}@{org.slug}.test",
            display_name=name,
            role=role,
            password_hash=password_hash,
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
    """Which user requests are made as: setting `user` sends that user's real access token."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None
        self._user: User | None = None
        self.session: AsyncSession | None = None  # the test's DB session (for arranging data)
        self.jobq: FakeQueue | None = None
        self.llm: FakeLlm | None = None
        self.settings = settings

    @property
    def user(self) -> User | None:
        return self._user

    @user.setter
    def user(self, user: User | None) -> None:
        assert self._client is not None
        self._user = user
        if user is None:
            self._client.headers.pop("Authorization", None)
        else:
            token = create_token(self._settings, user.id, TokenType.ACCESS)
            self._client.headers["Authorization"] = f"Bearer {token}"


@pytest.fixture
def acting(test_settings: Settings) -> ActingUser:
    return ActingUser(test_settings)


class FakeLlm:
    """Stands in for the configured LLM: set `model` (e.g. a pydantic-ai FunctionModel) to
    enable the AI endpoints in a test. Unset = no API key configured (503)."""

    def __init__(self) -> None:
        self.model: Model | None = None


@pytest.fixture
def llm() -> FakeLlm:
    return FakeLlm()


class FakeQueue:
    """Stands in for Celery/Redis: records the job ids handed to the queue (nothing runs).
    Tests run jobs explicitly via `app.services.jobs.run`."""

    def __init__(self) -> None:
        self.ids: list[uuid.UUID] = []
        self.broken = False

    def __call__(self, job_id: uuid.UUID) -> None:
        if self.broken:
            raise ConnectionError("broker down")
        self.ids.append(job_id)


@pytest.fixture
def jobq() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
async def http(
    test_settings: Settings,
    db_session: AsyncSession,
    acting: ActingUser,
    llm: FakeLlm,
    jobq: FakeQueue,
) -> AsyncIterator[AsyncClient]:
    app = create_app(test_settings)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _model() -> Model:
        if llm.model is None:
            return get_llm_model(test_settings)  # raises 503: no API key in tests
        return llm.model

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_llm_model] = _model
    app.dependency_overrides[get_job_enqueuer] = lambda: jobq
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        acting._client = client
        acting.session = db_session
        acting.jobq = jobq
        yield client
