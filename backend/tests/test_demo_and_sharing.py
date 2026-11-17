"""One-click demo sign-in and the clinician's per-client sharing overview ("new summary")."""

from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    AuditLog,
    CareAssignment,
    Organization,
    Summary,
    SummaryStatus,
    User,
    UserRole,
)

API = "/api/v1"


@dataclass
class Demo:
    org: Organization
    admin: User
    elif_: User
    mert: User
    ayse: User
    can: User
    assignment: CareAssignment
    other_admin: User
    other_clinician: User
    other_client: User


@pytest.fixture
async def demo(make_org, make_user, db_session: AsyncSession) -> Demo:
    org, other = await make_org("demo-clinic"), await make_org("other-clinic")
    d = Demo(
        org=org,
        admin=await make_user(org, UserRole.ORG_ADMIN, "admin"),
        elif_=await make_user(org, UserRole.CLINICIAN, "dr.elif"),
        mert=await make_user(org, UserRole.CLINICIAN, "dr.mert"),
        ayse=await make_user(org, UserRole.CLIENT, "client.ayse"),
        can=await make_user(org, UserRole.CLIENT, "client.can"),
        assignment=CareAssignment(organization_id=org.id),
        other_admin=await make_user(other, UserRole.ORG_ADMIN, "admin"),
        other_clinician=await make_user(other, UserRole.CLINICIAN, "dr.selin"),
        other_client=await make_user(other, UserRole.CLIENT, "client.emre"),
    )
    d.assignment.clinician_id, d.assignment.client_id = d.elif_.id, d.ayse.id
    db_session.add_all(
        [
            d.assignment,
            CareAssignment(organization_id=org.id, clinician_id=d.mert.id, client_id=d.can.id),
            CareAssignment(
                organization_id=other.id,
                clinician_id=d.other_clinician.id,
                client_id=d.other_client.id,
            ),
        ]
    )
    await db_session.flush()
    return d


@pytest.fixture
def demo_on(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(test_settings, "demo_login_enabled", True)
    return test_settings


async def _demo_login(http: AsyncClient, role: str):
    return await http.post(f"{API}/auth/demo-login", json={"role": role})


# --- Demo sign-in ----------------------------------------------------------------------


async def test_demo_login_is_off_by_default(http: AsyncClient, demo: Demo) -> None:
    assert (await http.get(f"{API}/auth/demo-login")).json() == {"enabled": False}
    for role in ("client", "clinician", "org_admin"):
        assert (await _demo_login(http, role)).status_code == 404


@pytest.mark.usefixtures("demo_on")
async def test_demo_login_signs_into_the_seeded_account_of_each_role(
    http: AsyncClient, demo: Demo, db_session: AsyncSession
) -> None:
    assert (await http.get(f"{API}/auth/demo-login")).json() == {"enabled": True}
    expected = {
        "client": demo.ayse,
        "clinician": demo.elif_,
        "org_admin": demo.admin,
    }
    for role, user in expected.items():
        response = await _demo_login(http, role)
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        me = await http.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["id"] == str(user.id)
        assert me.json()["role"] == role
        # The refresh token works like a normal session's.
        refreshed = await http.post(
            f"{API}/auth/refresh", json={"refresh_token": response.json()["refresh_token"]}
        )
        assert refreshed.status_code == 200

    audits = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.demo_login"))
    ).all()
    assert sorted(a.detail["role"] for a in audits) == ["client", "clinician", "org_admin"]
    assert {a.actor_id for a in audits} == {demo.ayse.id, demo.elif_.id, demo.admin.id}


@pytest.mark.usefixtures("demo_on")
async def test_demo_login_rejects_unknown_roles_and_any_other_input(
    http: AsyncClient, demo: Demo
) -> None:
    for body in ({"role": "admin"}, {"role": "superuser"}, {}, {"email": demo.can.email}):
        assert (await http.post(f"{API}/auth/demo-login", json=body)).status_code == 422


@pytest.mark.usefixtures("demo_on")
async def test_demo_login_needs_the_active_demo_clinic_account(
    http: AsyncClient, demo: Demo, db_session: AsyncSession
) -> None:
    demo.ayse.is_active = False
    await db_session.flush()
    assert (await _demo_login(http, "client")).status_code == 404
    # Another organization's accounts are never reachable, whatever their role.
    await db_session.delete(demo.admin)
    await db_session.flush()
    assert (await _demo_login(http, "org_admin")).status_code == 404


async def test_demo_login_is_rate_limited_per_ip(
    http: AsyncClient, demo: Demo, demo_on: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo_on, "rate_limit_demo_login", "2/minute")
    assert (await _demo_login(http, "client")).status_code == 200
    assert (await _demo_login(http, "clinician")).status_code == 200
    blocked = await _demo_login(http, "org_admin")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.usefixtures("demo_on")
async def test_demo_accounts_are_protected_from_the_demo_admin(
    http: AsyncClient, acting, demo: Demo
) -> None:
    acting.user = demo.admin
    for user in (demo.ayse, demo.elif_):
        response = await http.patch(f"{API}/admin/users/{user.id}", json={"is_active": False})
        assert response.status_code == 409
    response = await http.delete(f"{API}/admin/assignments/{demo.assignment.id}")
    assert response.status_code == 409
    # Everything else stays manageable.
    assert (
        await http.patch(f"{API}/admin/users/{demo.can.id}", json={"is_active": False})
    ).status_code == 200
    assert (
        await http.patch(f"{API}/admin/users/{demo.ayse.id}", json={"is_active": True})
    ).status_code == 200


async def test_demo_accounts_are_ordinary_when_demo_login_is_off(
    http: AsyncClient, acting, demo: Demo
) -> None:
    acting.user = demo.admin
    assert (await http.delete(f"{API}/admin/assignments/{demo.assignment.id}")).status_code == 204
    assert (
        await http.patch(f"{API}/admin/users/{demo.ayse.id}", json={"is_active": False})
    ).status_code == 200


# --- Clinician sharing overview --------------------------------------------------------


async def _approved_summary(acting, http: AsyncClient, client: User, title: str) -> str:
    session = acting.session
    summary = Summary(
        organization_id=client.organization_id,
        client_id=client.id,
        title=title,
        body="Synthetic text",
        status=SummaryStatus.DRAFT,
    )
    session.add(summary)
    await session.flush()
    acting.user = client
    assert (await http.post(f"{API}/summaries/{summary.id}/approve")).status_code == 200
    return str(summary.id)


def _row(clients: list[dict], client: User) -> dict:
    return next(c for c in clients if c["id"] == str(client.id))


async def test_clinician_sees_last_share_and_new_summaries(
    http: AsyncClient, acting, demo: Demo
) -> None:
    first = await _approved_summary(acting, http, demo.ayse, "One")
    second = await _approved_summary(acting, http, demo.ayse, "Two")
    private = await _approved_summary(acting, http, demo.ayse, "Never shared")
    acting.user = demo.ayse
    await http.post(f"{API}/summaries/{first}/share")
    shared = (await http.post(f"{API}/summaries/{second}/share")).json()

    acting.user = demo.elif_
    row = _row((await http.get(f"{API}/clinician/clients")).json(), demo.ayse)
    assert row["new_summaries"] == 2
    assert row["last_shared_at"] == shared["shared_at"]
    listed = {s["id"]: s["is_new"] for s in (await http.get(f"{API}/clinician/summaries")).json()}
    assert listed == {first: True, second: True}
    assert private not in listed

    # Opening a summary marks it read for this clinician only.
    assert (await http.get(f"{API}/clinician/summaries/{first}")).status_code == 200
    assert (
        _row((await http.get(f"{API}/clinician/clients")).json(), demo.ayse)["new_summaries"] == 1
    )
    listed = {s["id"]: s["is_new"] for s in (await http.get(f"{API}/clinician/summaries")).json()}
    assert listed == {first: False, second: True}

    # Sharing again makes it new again.
    acting.user = demo.ayse
    await http.post(f"{API}/summaries/{first}/share")
    acting.user = demo.elif_
    assert (
        _row((await http.get(f"{API}/clinician/clients")).json(), demo.ayse)["new_summaries"] == 2
    )

    # Revoking removes it from the count and the last-share date.
    acting.user = demo.ayse
    await http.post(f"{API}/summaries/{first}/unshare")
    await http.post(f"{API}/summaries/{second}/unshare")
    acting.user = demo.elif_
    row = _row((await http.get(f"{API}/clinician/clients")).json(), demo.ayse)
    assert row["new_summaries"] == 0
    assert row["last_shared_at"] is None


async def test_sharing_overview_never_leaks_to_other_clinicians_or_orgs(
    http: AsyncClient, acting, demo: Demo
) -> None:
    sid = await _approved_summary(acting, http, demo.ayse, "Mine")
    await http.post(f"{API}/summaries/{sid}/share")

    # Dr. Mert (same org, not assigned to Ayşe) and the other clinic see nothing of it.
    for clinician in (demo.mert, demo.other_clinician):
        acting.user = clinician
        clients = (await http.get(f"{API}/clinician/clients")).json()
        assert str(demo.ayse.id) not in {c["id"] for c in clients}
        assert all(c["new_summaries"] == 0 and c["last_shared_at"] is None for c in clients)
        assert (await http.get(f"{API}/clinician/summaries")).json() == []

    # A read by Dr. Elif does not mark it read for a second assigned clinician.
    acting.session.add(
        CareAssignment(
            organization_id=demo.org.id, clinician_id=demo.mert.id, client_id=demo.ayse.id
        )
    )
    await acting.session.flush()
    acting.user = demo.ayse
    await http.post(f"{API}/summaries/{sid}/share")  # shared after Mert's assignment
    acting.user = demo.elif_
    await http.get(f"{API}/clinician/summaries/{sid}")
    acting.user = demo.mert
    assert (
        _row((await http.get(f"{API}/clinician/clients")).json(), demo.ayse)["new_summaries"] == 1
    )

    # The org admin still sees no clinical content or sharing metadata.
    acting.user = demo.admin
    assert (await http.get(f"{API}/clinician/clients")).status_code == 403
