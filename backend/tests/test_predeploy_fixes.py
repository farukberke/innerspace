"""Regression tests for the pre-deploy security review: sharing bound to the assignment,
trusted-proxy client IP, refresh token rotation/logout, fail-closed limiter, prod docs,
invitation e-mail oracle."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.config import Settings
from app.core.ratelimit import (
    FAIL_CLOSED_SCOPES,
    Limit,
    RateLimiter,
    build_rate_limiter,
)
from app.main import create_app
from app.models import AuditLog, RefreshToken
from app.services.errors import RateLimiterUnavailableError
from tests.conftest import TEST_JWT_SECRET
from tests.test_auth_rbac import API, _accept, _invite, _login, _summary
from tests.test_auth_rbac import w as w  # noqa: PLC0414  (fixture re-export)


@pytest.fixture
def make_client(
    test_settings: Settings, db_session: AsyncSession
) -> Callable[..., AsyncIterator[AsyncClient]]:
    """An app with overridden settings, sharing the test's DB session."""

    def _make(**overrides: object) -> AsyncClient:
        app = create_app(test_settings.model_copy(update=overrides))

        async def _session() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_session] = _session
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _make


# --- 1. Sharing is not inherited by clinicians assigned later --------------------------


async def test_clinician_assigned_after_sharing_sees_nothing_until_reshared(
    http: AsyncClient, acting, w
) -> None:
    sid = await _summary(http, acting, w.client_a)
    assert (await http.post(f"{API}/summaries/{sid}/share")).status_code == 200

    # The org admin assigns another clinician afterwards.
    acting.user = w.admin_a
    body = {"clinician_id": str(w.clin_a2.id), "client_id": str(w.client_a.id)}
    assert (await http.post(f"{API}/admin/assignments", json=body)).status_code == 201

    acting.user = w.clin_a2
    assert (await http.get(f"{API}/clinician/summaries")).json() == []
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 404
    acting.user = w.clin_a  # the original clinician is unaffected
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 200

    # The client shares again: now the new clinician sees it.
    acting.user = w.client_a
    assert (await http.post(f"{API}/summaries/{sid}/share")).status_code == 200
    acting.user = w.clin_a2
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 200
    assert [s["id"] for s in (await http.get(f"{API}/clinician/summaries")).json()] == [sid]


async def test_reassigned_clinician_needs_a_fresh_share(http: AsyncClient, acting, w) -> None:
    sid = await _summary(http, acting, w.client_a)
    await http.post(f"{API}/summaries/{sid}/share")
    acting.user = w.admin_a
    assignments = (await http.get(f"{API}/admin/assignments")).json()
    assert (await http.delete(f"{API}/admin/assignments/{assignments[0]['id']}")).status_code == 204
    body = {"clinician_id": str(w.clin_a.id), "client_id": str(w.client_a.id)}
    assert (await http.post(f"{API}/admin/assignments", json=body)).status_code == 201
    acting.user = w.clin_a
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 404


async def test_client_invited_with_assignment_still_sees_later_shares(
    http: AsyncClient, acting, w
) -> None:
    acting.user = w.clin_a2
    token = (await _invite(http, email="fresh@org-a.test")).json()["token"]
    acting.user = None
    user = (await _accept(http, token)).json()
    from app.models import User  # noqa: PLC0415

    client = await acting.session.get(User, user["id"])
    sid = await _summary(http, acting, client)
    await http.post(f"{API}/summaries/{sid}/share")
    acting.user = w.clin_a2
    assert (await http.get(f"{API}/clinician/summaries/{sid}")).status_code == 200


# --- 2. Client IP / trusted proxies ------------------------------------------------------


async def _login_status(client: AsyncClient, n: int, xff: str | None) -> int:
    headers = {"X-Forwarded-For": xff} if xff else {}
    response = await client.post(
        f"{API}/auth/login",
        json={"email": f"nobody{n}@nowhere.test", "password": "x"},
        headers=headers,
    )
    return response.status_code


async def test_spoofed_left_xff_entries_do_not_bypass_limit(make_client) -> None:
    async with make_client(trusted_proxy_hops=1, rate_limit_login_ip="2/minute") as client:
        codes = [await _login_status(client, i, f"10.0.0.{i}, 203.0.113.9") for i in range(4)]
    assert codes == [401, 401, 429, 429]


async def test_distinct_real_clients_get_separate_buckets(make_client) -> None:
    async with make_client(trusted_proxy_hops=1, rate_limit_login_ip="1/minute") as client:
        assert await _login_status(client, 1, "198.51.100.1") == 401
        assert await _login_status(client, 2, "198.51.100.1") == 429
        assert await _login_status(client, 3, "198.51.100.2") == 401  # a different client


async def test_two_hops_use_second_entry_from_the_right(make_client) -> None:
    async with make_client(trusted_proxy_hops=2, rate_limit_login_ip="1/minute") as client:
        assert await _login_status(client, 1, "evil-1, 203.0.113.5, 10.1.1.1") == 401
        assert await _login_status(client, 2, "evil-2, 203.0.113.5, 10.1.1.2") == 429


async def test_xff_is_ignored_without_trusted_hops(make_client) -> None:
    async with make_client(trusted_proxy_hops=0, rate_limit_login_ip="2/minute") as client:
        codes = [await _login_status(client, i, f"203.0.113.{i}") for i in range(4)]
    assert codes == [401, 401, 429, 429]  # all share the TCP peer's bucket


async def test_short_or_missing_xff_falls_back_to_the_peer(make_client) -> None:
    async with make_client(trusted_proxy_hops=2, rate_limit_login_ip="1/minute") as client:
        assert await _login_status(client, 1, None) == 401
        assert await _login_status(client, 2, "203.0.113.5") == 429  # fewer entries than hops


# --- 3. Refresh rotation, logout, absolute lifetime ---------------------------------------


async def _tokens(http: AsyncClient, w) -> dict[str, str]:
    return (await _login(http, w.client_a.email)).json()


async def _refresh(http: AsyncClient, token: str):
    return await http.post(f"{API}/auth/refresh", json={"refresh_token": token})


async def test_refresh_rotates_and_reuse_revokes_the_family(
    http: AsyncClient, w, db_session: AsyncSession
) -> None:
    first = await _tokens(http, w)
    second = (await _refresh(http, first["refresh_token"])).json()
    assert second["refresh_token"] != first["refresh_token"]
    third = (await _refresh(http, second["refresh_token"])).json()

    # Replaying an old token: rejected, and the whole family (including the newest) dies.
    assert (await _refresh(http, first["refresh_token"])).status_code == 401
    assert (await _refresh(http, third["refresh_token"])).status_code == 401
    rows = list(await db_session.scalars(select(RefreshToken)))
    assert len(rows) == 3 and all(r.revoked_at is not None for r in rows)
    actions = list(await db_session.scalars(select(AuditLog.action)))
    assert "auth.refresh_reuse_detected" in actions and "auth.refresh" in actions


async def test_other_sessions_are_not_affected_by_family_revocation(http: AsyncClient, w) -> None:
    a, b = await _tokens(http, w), await _tokens(http, w)
    assert (await _refresh(http, a["refresh_token"])).status_code == 200
    assert (await _refresh(http, a["refresh_token"])).status_code == 401
    assert (await _refresh(http, b["refresh_token"])).status_code == 200


async def test_logout_revokes_refresh_token(http: AsyncClient, w, db_session: AsyncSession) -> None:
    tokens = await _tokens(http, w)
    renewed = (await _refresh(http, tokens["refresh_token"])).json()
    out = await http.post(f"{API}/auth/logout", json={"refresh_token": renewed["refresh_token"]})
    assert out.status_code == 204
    assert (await _refresh(http, renewed["refresh_token"])).status_code == 401
    # Idempotent; garbage tokens are a no-op, not an error.
    again = await http.post(f"{API}/auth/logout", json={"refresh_token": renewed["refresh_token"]})
    assert again.status_code == 204
    junk = await http.post(f"{API}/auth/logout", json={"refresh_token": "not-a-jwt"})
    assert junk.status_code == 204
    assert "auth.logout" in list(await db_session.scalars(select(AuditLog.action)))


async def test_refresh_rejects_token_not_in_database(http: AsyncClient, w, test_settings) -> None:
    from app.core.security import TokenType, create_token  # noqa: PLC0415

    forged = create_token(test_settings, w.client_a.id, TokenType.REFRESH)  # valid JWT, no row
    assert (await _refresh(http, forged)).status_code == 401


async def test_absolute_session_lifetime_is_enforced(
    http: AsyncClient, w, db_session: AsyncSession, test_settings: Settings
) -> None:
    tokens = await _tokens(http, w)
    long_ago = datetime.now(UTC) - timedelta(days=test_settings.session_max_days + 1)
    await db_session.execute(update(RefreshToken).values(family_started_at=long_ago))
    assert (await _refresh(http, tokens["refresh_token"])).status_code == 401


async def test_new_refresh_tokens_never_outlive_the_session(
    http: AsyncClient, w, db_session: AsyncSession, test_settings: Settings
) -> None:
    tokens = await _tokens(http, w)
    started = datetime.now(UTC) - timedelta(days=test_settings.session_max_days - 1)
    await db_session.execute(update(RefreshToken).values(family_started_at=started))
    assert (await _refresh(http, tokens["refresh_token"])).status_code == 200
    newest = await db_session.scalar(select(RefreshToken).where(RefreshToken.used_at.is_(None)))
    assert newest is not None
    limit = started + timedelta(days=test_settings.session_max_days)
    assert abs((newest.expires_at - limit).total_seconds()) < 1  # capped, not now + 7 days


# --- 4. Fail-closed limiter in production --------------------------------------------------


class _Broken:
    async def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        raise ConnectionError("redis down")

    async def close(self) -> None: ...


@pytest.mark.parametrize("scope", sorted(FAIL_CLOSED_SCOPES))
async def test_credential_scopes_fail_closed_when_backend_is_down(scope: str) -> None:
    limiter = RateLimiter(_Broken(), fail_closed_scopes=FAIL_CLOSED_SCOPES)
    with pytest.raises(RateLimiterUnavailableError):
        await limiter.check(scope, "x", Limit(1, 60))


async def test_other_scopes_stay_fail_open() -> None:
    limiter = RateLimiter(_Broken(), fail_closed_scopes=FAIL_CLOSED_SCOPES)
    await limiter.check("generate", "x", Limit(1, 60))


def test_only_production_limiter_fails_closed(test_settings: Settings) -> None:
    prod = test_settings.model_copy(update={"app_env": "production", "rate_limit_backend": "redis"})
    dev = test_settings.model_copy(update={"app_env": "development", "rate_limit_backend": "redis"})
    assert build_rate_limiter(prod)._fail_closed_scopes == FAIL_CLOSED_SCOPES
    assert build_rate_limiter(dev)._fail_closed_scopes == frozenset()


async def test_login_answers_503_with_retry_after_when_limiter_is_down(make_client) -> None:
    async with make_client() as client:
        client._transport.app.state.rate_limiter = RateLimiter(  # type: ignore[attr-defined]
            _Broken(), fail_closed_scopes=FAIL_CLOSED_SCOPES
        )
        response = await client.post(
            f"{API}/auth/login", json={"email": "a@b.test", "password": "x"}
        )
    assert response.status_code == 503
    assert int(response.headers["Retry-After"]) >= 1


def test_production_rejects_memory_rate_limiter() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_BACKEND"):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://x/y",
            jwt_secret=TEST_JWT_SECRET,
            rate_limit_backend="memory",
        )
    Settings(  # the same in development is fine
        app_env="development",
        database_url="postgresql+asyncpg://x/y",
        jwt_secret=TEST_JWT_SECRET,
        rate_limit_backend="memory",
    )


# --- 5. API docs are off in production ---------------------------------------------------


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_docs_are_not_served_in_production(test_settings: Settings, path: str) -> None:
    settings = test_settings.model_copy(
        update={"app_env": "production", "rate_limit_backend": "redis"}
    )
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404


async def test_docs_are_served_outside_production(http: AsyncClient) -> None:
    assert (await http.get("/openapi.json")).status_code == 200


# --- 6. Invitation e-mail oracle ----------------------------------------------------------


async def test_invitation_does_not_reveal_emails_registered_in_other_orgs(
    http: AsyncClient, acting, w
) -> None:
    acting.user = w.admin_a
    foreign = await _invite(http, email=w.client_b.email, role="client")
    fresh = await _invite(http, email="brand-new@org-a.test", role="client")
    assert foreign.status_code == fresh.status_code == 201
    assert set(foreign.json()) == set(fresh.json())

    acting.user = None
    refused = await _accept(http, foreign.json()["token"])
    assert refused.status_code == 400
    assert refused.json() == (await _accept(http, "garbage-token")).json()  # generic error


async def test_same_org_duplicate_is_still_reported(http: AsyncClient, acting, w) -> None:
    acting.user = w.admin_a
    assert (await _invite(http, email=w.client_a2.email, role="client")).status_code == 409
