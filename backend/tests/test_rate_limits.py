"""Rate limiting (login brute force, refresh, invitation, AI endpoints) and the per-user daily
LLM budget. The limiter runs on the in-memory backend (conftest); Redis is stubbed in unit tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import Settings
from app.core.ratelimit import (
    Limit,
    MemoryBackend,
    RateLimiter,
    RedisBackend,
    parse_limit,
)
from app.models import LlmUsage, SummaryJob
from app.services.errors import RateLimitedError
from tests.conftest import TEST_JWT_SECRET, TEST_PASSWORD, FakeLlm, FakeQueue
from tests.test_ai import API, PERIOD, Script, World, after_output, draft
from tests.test_ai import w as ai_world

w = ai_world  # shared world fixture, re-exported so pytest finds it here


def _period(day: int) -> dict[str, str]:
    return {"period_start": f"2026-11-{day:02d}", "period_end": f"2026-11-{day:02d}"}


def _assert_429(response, *, minimum: int = 1) -> None:
    assert response.status_code == 429, response.text
    assert int(response.headers["Retry-After"]) >= minimum
    assert response.json()["error_code"] == "rate_limited"


# --- Unit: parsing, windows, backends --------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("10/minute", Limit(10, 60)),
        ("8/15minute", Limit(8, 900)),
        ("3/hours", Limit(3, 3600)),
        ("1/day", Limit(1, 86400)),
        ("5/second", Limit(5, 1)),
    ],
)
def test_parse_limit(spec: str, expected: Limit) -> None:
    assert parse_limit(spec) == expected


@pytest.mark.parametrize("spec", ["", "ten/minute", "0/minute", "5/0minute", "5/fortnight", "5"])
def test_parse_limit_rejects_garbage(spec: str) -> None:
    with pytest.raises(ValueError, match="rate limit"):
        parse_limit(spec)


def test_invalid_limit_in_settings_fails_at_startup(test_settings: Settings) -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+asyncpg://x/y",
            jwt_secret=TEST_JWT_SECRET,
            rate_limit_login_ip="lots",
        )


async def test_window_expires_and_counts_per_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    limiter = RateLimiter(MemoryBackend())
    limit = Limit(2, 60)
    await limiter.check("x", "a", limit)
    await limiter.check("x", "a", limit)
    with pytest.raises(RateLimitedError) as exc:
        await limiter.check("x", "a", limit)
    assert 1 <= exc.value.retry_after <= 61
    await limiter.check("x", "b", limit)  # another identity is independent
    await limiter.check("y", "a", limit)  # another scope is independent
    now[0] += 61
    await limiter.check("x", "a", limit)  # the window has passed


async def test_identity_is_hashed_in_keys() -> None:
    backend = MemoryBackend()
    await RateLimiter(backend).check("login_email", "Victim@Example.com", Limit(5, 60))
    (key,) = backend._windows
    assert "example" not in key.lower() and key.startswith("rl:login_email:")


async def test_limiter_fails_open_when_backend_is_down(caplog: pytest.LogCaptureFixture) -> None:
    class Broken:
        async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
            raise ConnectionError("redis down")

        async def close(self) -> None: ...

    await RateLimiter(Broken()).check("x", "a", Limit(1, 60))
    await RateLimiter(Broken()).check("x", "a", Limit(1, 60))  # never raises
    assert "rate limiter unavailable" in caplog.text


async def test_redis_backend_sets_expiry_and_repairs_missing_ttl() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
            self.ttls: dict[str, int] = {}
            self.expired: list[tuple[str, int]] = []

        async def incr(self, key: str) -> int:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, key: str, seconds: int) -> None:
            self.ttls[key] = seconds
            self.expired.append((key, seconds))

        async def ttl(self, key: str) -> int:
            return self.ttls.get(key, -1)

        async def aclose(self) -> None: ...

    backend = RedisBackend("redis://localhost:1/0")
    await backend._redis.aclose()
    fake = FakeRedis()
    backend._redis = fake  # type: ignore[assignment]
    assert await backend.hit("k", 60) == (1, 60)
    assert await backend.hit("k", 60) == (2, 60)
    assert fake.expired == [("k", 60)]  # expiry is only set when the window starts
    fake.ttls.clear()  # a crash between INCR and EXPIRE left the key without a TTL
    assert await backend.hit("k", 60) == (3, 60)


# --- HTTP: login brute force -----------------------------------------------------------


async def _login(http: AsyncClient, email: str, password: str = "wrong-password-123"):  # noqa: S107
    return await http.post(f"{API}/auth/login", json={"email": email, "password": password})


async def test_login_brute_force_on_one_account_is_limited_per_email(
    http: AsyncClient, w: World, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_login_email", "5/15minute")
    for _ in range(5):
        assert (await _login(http, w.client.email)).status_code == 401
    blocked = await _login(http, w.client.email)
    _assert_429(blocked, minimum=60)
    assert "wrong-password" not in blocked.text and w.client.email not in blocked.text
    # Even the right password is refused while the account is locked down...
    assert (await _login(http, w.client.email, TEST_PASSWORD)).status_code == 429
    # ...case differences do not create a new bucket...
    assert (await _login(http, w.client.email.upper())).status_code == 429
    # ...but other accounts are unaffected.
    assert (await _login(http, w.clinician.email, TEST_PASSWORD)).status_code == 200


async def test_login_is_limited_per_source_ip_across_emails(
    http: AsyncClient, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_login_ip", "4/minute")
    for i in range(4):
        assert (await _login(http, f"guess{i}@nowhere.test")).status_code == 401
    _assert_429(await _login(http, "guess99@nowhere.test"))


async def test_unknown_and_known_accounts_are_throttled_identically(
    http: AsyncClient, w: World, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_login_email", "2/minute")
    for email in (w.client.email, "ghost@nowhere.test"):
        assert (await _login(http, email)).status_code == 401
        assert (await _login(http, email)).status_code == 401
        _assert_429(await _login(http, email))


async def test_refresh_and_accept_invitation_are_limited(
    http: AsyncClient, monkeypatch: pytest.MonkeyPatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_refresh", "2/minute")
    monkeypatch.setattr(test_settings, "rate_limit_accept_invitation", "2/minute")
    for _ in range(2):
        assert (
            await http.post(f"{API}/auth/refresh", json={"refresh_token": "x" * 20})
        ).status_code == 401
    _assert_429(await http.post(f"{API}/auth/refresh", json={"refresh_token": "x" * 20}))

    body = {"token": "t" * 30, "password": "a-long-enough-password", "display_name": "X"}
    for _ in range(2):
        assert (await http.post(f"{API}/auth/accept-invitation", json=body)).status_code == 400
    _assert_429(await http.post(f"{API}/auth/accept-invitation", json=body))


# --- HTTP: AI endpoints ----------------------------------------------------------------


async def test_generate_is_limited_per_user_and_no_job_is_created_over_the_limit(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    jobq: FakeQueue,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_generate", "2/hour")
    llm.model = Script(draft()).model
    acting.user = w.client
    for day in (1, 2):
        assert (await http.post(f"{API}/summaries/generate", json=_period(day))).status_code == 202
    _assert_429(await http.post(f"{API}/summaries/generate", json=_period(3)), minimum=60)
    assert len(jobq.ids) == 2
    assert (await db_session.scalar(select(func.count()).select_from(SummaryJob))) == 2
    # Another user has their own budget.
    acting.user = w.client_same_org
    assert (await http.post(f"{API}/summaries/generate", json=_period(3))).status_code == 202


async def test_unauthenticated_and_wrong_role_requests_do_not_use_the_limit(
    http: AsyncClient, acting, llm: FakeLlm, w: World, monkeypatch, test_settings: Settings
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_generate", "1/hour")
    llm.model = Script(draft()).model
    for _ in range(3):
        assert (await http.post(f"{API}/summaries/generate", json=PERIOD)).status_code == 401
    acting.user = w.client
    assert (await http.post(f"{API}/summaries/generate", json=PERIOD)).status_code == 202


async def test_after_session_notes_are_limited_per_user(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "rate_limit_after_session", "2/hour")
    llm.model = Script(after_output(discussed=["sleep"])).model
    acting.user = w.client
    for _ in range(2):
        assert (
            await http.post(f"{API}/after-session-notes", json={"text": "we talked about sleep"})
        ).status_code == 201
    _assert_429(await http.post(f"{API}/after-session-notes", json={"text": "more"}))


# --- Daily LLM budget ------------------------------------------------------------------


def _usage(user, *, requests: int = 1, cost: str = "0.01", age_hours: float = 1) -> LlmUsage:
    return LlmUsage(
        organization_id=user.organization_id,
        user_id=user.id,
        purpose="session_summary",
        model="test",
        input_tokens=10,
        output_tokens=10,
        requests=requests,
        cost_usd=Decimal(cost),
        duration_ms=1,
        success=True,
        created_at=datetime.now(UTC) - timedelta(hours=age_hours),
    )


async def test_daily_request_budget_blocks_job_creation(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    jobq: FakeQueue,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "llm_daily_request_limit", 10)
    db_session.add_all([_usage(w.client, requests=6), _usage(w.client, requests=4)])
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.user = w.client
    blocked = await http.post(f"{API}/summaries/generate", json=PERIOD)
    _assert_429(blocked, minimum=60)
    assert jobq.ids == []
    assert (await db_session.scalar(select(func.count()).select_from(SummaryJob))) == 0
    # The after-session endpoint shares the budget.
    over = await http.post(f"{API}/after-session-notes", json={"text": "notes"})
    _assert_429(over)
    # Another user is not affected.
    acting.user = w.client_same_org
    assert (await http.post(f"{API}/summaries/generate", json=PERIOD)).status_code == 202


async def test_daily_cost_budget_blocks_job_creation(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    jobq: FakeQueue,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "llm_daily_cost_limit_usd", 1.0)
    db_session.add(_usage(w.client, cost="1.250000"))
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.user = w.client
    _assert_429(await http.post(f"{API}/summaries/generate", json=PERIOD))
    assert jobq.ids == []


async def test_usage_older_than_24h_and_zero_limits_do_not_block(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "llm_daily_request_limit", 5)
    db_session.add(_usage(w.client, requests=50, cost="50", age_hours=30))
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.user = w.client
    assert (await http.post(f"{API}/summaries/generate", json=_period(1))).status_code == 202
    # Recent heavy use blocks, until the cap is disabled with 0.
    db_session.add(_usage(w.client, requests=50))
    await db_session.flush()
    _assert_429(await http.post(f"{API}/summaries/generate", json=_period(2)))
    monkeypatch.setattr(test_settings, "llm_daily_request_limit", 0)
    monkeypatch.setattr(test_settings, "llm_daily_cost_limit_usd", 0)
    assert (await http.post(f"{API}/summaries/generate", json=_period(3))).status_code == 202


async def test_retry_after_reflects_when_the_oldest_usage_leaves_the_window(
    http: AsyncClient,
    acting,
    llm: FakeLlm,
    w: World,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
) -> None:
    monkeypatch.setattr(test_settings, "llm_daily_request_limit", 1)
    db_session.add(_usage(w.client, age_hours=23))  # leaves the 24h window in about an hour
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.user = w.client
    response = await http.post(f"{API}/summaries/generate", json=PERIOD)
    assert 3000 <= int(response.headers["Retry-After"]) <= 3700
