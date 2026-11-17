"""The clinician's per-client sharing overview ("new summary")."""

from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
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
