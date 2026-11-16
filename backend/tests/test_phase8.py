"""Phase 8: summary topics, in-app reminders, data export and account deletion."""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AfterSessionNote,
    Appointment,
    AppointmentKind,
    AuditLog,
    CareAssignment,
    Entry,
    EntryKind,
    Invitation,
    LlmUsage,
    Organization,
    RefreshToken,
    Summary,
    SummaryCitation,
    SummaryJob,
    SummaryStatement,
    SummaryStatus,
    SupportPlan,
    User,
    UserRole,
)
from app.services import reminders
from tests.conftest import TEST_PASSWORD

API = "/api/v1"
CRISIS_TEXT = "Kendime zarar vermek istiyorum"
IST = ZoneInfo("Europe/Istanbul")


@dataclass
class World:
    org_a: Organization
    admin: User
    clin: User
    other_clin: User  # same org, not assigned
    client: User
    client2: User  # same org
    client_b: User  # other org
    clin_b: User


@pytest.fixture
async def w(make_user, db_session: AsyncSession, org_a, org_b) -> World:
    clin = await make_user(org_a, UserRole.CLINICIAN, "clin")
    client = await make_user(org_a, UserRole.CLIENT, "client")
    client2 = await make_user(org_a, UserRole.CLIENT, "client2")
    clin_b = await make_user(org_b, UserRole.CLINICIAN, "clin-b")
    db_session.add_all(
        [
            CareAssignment(
                organization_id=org_a.id,
                clinician_id=clin.id,
                client_id=client.id,
                created_at=datetime.now(UTC) - timedelta(days=1),
            ),
            CareAssignment(organization_id=org_a.id, clinician_id=clin.id, client_id=client2.id),
        ]
    )
    await db_session.flush()
    return World(
        org_a=org_a,
        admin=await make_user(org_a, UserRole.ORG_ADMIN, "admin"),
        clin=clin,
        other_clin=await make_user(org_a, UserRole.CLINICIAN, "other-clin"),
        client=client,
        client2=client2,
        client_b=await make_user(org_b, UserRole.CLIENT, "client-b"),
        clin_b=clin_b,
    )


async def _summary(
    db: AsyncSession, client: User, status: SummaryStatus = SummaryStatus.DRAFT, **kw
) -> Summary:
    summary = Summary(
        organization_id=client.organization_id,
        client_id=client.id,
        title="Özet",
        body="- x",
        status=status,
        shared_at=datetime.now(UTC) if status == SummaryStatus.SHARED else None,
        **kw,
    )
    db.add(summary)
    await db.flush()
    return summary


# --- Topics ------------------------------------------------------------------------------


async def test_client_sets_topics_and_edit_returns_summary_to_draft(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, SummaryStatus.APPROVED)
    acting.user = w.client
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": ["  Uyku düzenim ", "İş"]})
    assert r.status_code == 200, r.text
    assert r.json()["topics"] == ["Uyku düzenim", "İş"]
    assert r.json()["status"] == "draft"
    assert (await http.get(f"{API}/summaries/{s.id}")).json()["topics"] == ["Uyku düzenim", "İş"]
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": []})
    assert r.json()["topics"] == []


@pytest.mark.parametrize(
    "topics",
    [
        ["x"] * 11,
        ["a" * 201],
        [""],
        ["   "],
    ],
)
async def test_topics_limits(
    http: AsyncClient, acting, w: World, db_session: AsyncSession, topics: list[str]
) -> None:
    s = await _summary(db_session, w.client)
    acting.user = w.client
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": topics})
    assert r.status_code == 422


async def test_topics_exactly_at_limits_are_accepted(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client)
    acting.user = w.client
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": ["a" * 200] * 10})
    assert r.status_code == 200


async def test_topics_guardrail_violation_is_rejected_and_nothing_saved(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, topics=["eski"])
    acting.user = w.client
    r = await http.put(
        f"{API}/summaries/{s.id}/topics", json={"topics": ["Sertralin 100 mg olmalı"]}
    )
    assert r.status_code == 422
    assert (await http.get(f"{API}/summaries/{s.id}")).json()["topics"] == ["eski"]


async def test_topics_crisis_language_returns_fixed_crisis_response_and_saves_nothing(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, SummaryStatus.APPROVED)
    acting.user = w.client
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": [CRISIS_TEXT]})
    assert r.status_code == 200
    assert r.json()["crisis"] is True and r.json()["resources"]
    again = (await http.get(f"{API}/summaries/{s.id}")).json()
    assert again["topics"] == [] and again["status"] == "approved"
    audit = (
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "ai.crisis_detected"))
    ).all()
    assert len(audit) == 1 and audit[0].detail == {"source": "topics"}
    assert CRISIS_TEXT not in json.dumps(audit[0].detail)


async def test_topics_cannot_be_edited_while_shared(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, SummaryStatus.SHARED, topics=["a"])
    acting.user = w.client
    r = await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": ["b"]})
    assert r.status_code == 409
    await http.post(f"{API}/summaries/{s.id}/unshare")
    assert (
        await http.put(f"{API}/summaries/{s.id}/topics", json={"topics": ["b"]})
    ).status_code == 200


async def test_topics_only_for_own_summary_and_client_role(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client)
    url = f"{API}/summaries/{s.id}/topics"
    for other in (w.client2, w.client_b):  # same org and other org: indistinguishable 404
        acting.user = other
        assert (await http.put(url, json={"topics": ["x"]})).status_code == 404
    for forbidden in (w.clin, w.admin):
        acting.user = forbidden
        assert (await http.put(url, json={"topics": ["x"]})).status_code == 403
    acting.user = None
    assert (await http.put(url, json={"topics": ["x"]})).status_code == 401
    await db_session.refresh(s)
    assert s.topics == []


async def test_clinician_sees_topics_only_of_shared_summary(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, topics=["Uyku"])
    acting.user = w.clin
    assert (await http.get(f"{API}/clinician/summaries/{s.id}")).status_code == 404
    assert (await http.get(f"{API}/clinician/summaries")).json() == []

    acting.user = w.client
    assert (await http.post(f"{API}/summaries/{s.id}/approve")).status_code == 200
    assert (await http.post(f"{API}/summaries/{s.id}/share")).status_code == 200
    acting.user = w.clin
    shared = await http.get(f"{API}/clinician/summaries/{s.id}")
    assert shared.status_code == 200 and shared.json()["topics"] == ["Uyku"]
    acting.user = w.other_clin
    assert (await http.get(f"{API}/clinician/summaries/{s.id}")).status_code == 404
    acting.user = w.admin
    assert (await http.get(f"{API}/clinician/summaries/{s.id}")).status_code == 403

    acting.user = w.client
    await http.post(f"{API}/summaries/{s.id}/unshare")
    acting.user = w.clin
    assert (await http.get(f"{API}/clinician/summaries/{s.id}")).status_code == 404


async def test_approve_rechecks_topics_with_guardrails(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    s = await _summary(db_session, w.client, topics=["Dozu artırın"])  # bypassing the API
    acting.user = w.client
    assert (await http.post(f"{API}/summaries/{s.id}/approve")).status_code == 422


# --- Reminders ---------------------------------------------------------------------------


def _local_noon(day_offset: int) -> datetime:
    today = datetime.now(UTC).astimezone(IST).date()
    return datetime.combine(today + timedelta(days=day_offset), datetime.min.time(), IST).replace(
        hour=12
    )


async def _appointment(db: AsyncSession, w: World, client: User, at: datetime) -> Appointment:
    a = Appointment(
        organization_id=client.organization_id,
        client_id=client.id,
        clinician_id=w.clin.id if client.organization_id == w.org_a.id else w.clin_b.id,
        kind=AppointmentKind.THERAPY,
        scheduled_at=at,
    )
    db.add(a)
    await db.flush()
    return a


async def test_reminder_tomorrow_without_summary_then_gone_when_linked(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    a = await _appointment(db_session, w, w.client, _local_noon(1))
    acting.user = w.client
    items = (await http.get(f"{API}/reminders")).json()
    assert [(i["kind"], i["appointment_id"]) for i in items] == [("prepare_summary", str(a.id))]
    assert "hazırlanmak" in items[0]["message"]
    await _summary(db_session, w.client, appointment_id=a.id)
    assert (await http.get(f"{API}/reminders")).json() == []


async def test_reminder_yesterday_without_note_then_gone_when_note_exists(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    a = await _appointment(db_session, w, w.client, _local_noon(-1))
    acting.user = w.client
    items = (await http.get(f"{API}/reminders")).json()
    assert [(i["kind"], i["appointment_id"]) for i in items] == [("after_session_note", str(a.id))]
    db_session.add(
        AfterSessionNote(
            organization_id=w.org_a.id,
            client_id=w.client.id,
            source_text="not",
            created_at=a.scheduled_at + timedelta(hours=1),
        )
    )
    await db_session.flush()
    assert (await http.get(f"{API}/reminders")).json() == []


async def test_reminders_ignore_other_days_and_other_clients(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    await _appointment(db_session, w, w.client, _local_noon(0))  # today
    await _appointment(db_session, w, w.client, _local_noon(2))
    await _appointment(db_session, w, w.client, _local_noon(-2))
    # Other people's appointments, and another client's note/summary, change nothing.
    other = await _appointment(db_session, w, w.client2, _local_noon(1))
    await _appointment(db_session, w, w.client_b, _local_noon(-1))
    await _summary(db_session, w.client2, appointment_id=other.id)
    acting.user = w.client
    assert (await http.get(f"{API}/reminders")).json() == []
    acting.user = w.client2
    assert (await http.get(f"{API}/reminders")).json() == []  # own tomorrow has a summary
    acting.user = w.client_b
    assert [i["kind"] for i in (await http.get(f"{API}/reminders")).json()] == [
        "after_session_note"
    ]


async def test_reminders_are_client_only(http: AsyncClient, acting, w: World) -> None:
    for user in (w.clin, w.admin):
        acting.user = user
        assert (await http.get(f"{API}/reminders")).status_code == 403
    acting.user = None
    assert (await http.get(f"{API}/reminders")).status_code == 401


async def test_reminder_day_boundary_uses_the_clients_calendar_day(
    db_session: AsyncSession, w: World
) -> None:
    """Pinned: 'tomorrow' is the next calendar day in the reminder timezone, not 24 hours."""
    now = datetime(2026, 11, 17, 21, 30, tzinfo=UTC)  # 00:30 on 18 Nov in Istanbul (UTC+3)
    late = await _appointment(db_session, w, w.client, datetime(2026, 11, 19, 20, 59, tzinfo=UTC))
    early_next = await _appointment(
        db_session, w, w.client, datetime(2026, 11, 19, 21, 0, tzinfo=UTC)
    )  # 20 Nov 00:00 local: the day after tomorrow
    yesterday = await _appointment(
        db_session, w, w.client, datetime(2026, 11, 16, 21, 0, tzinfo=UTC)
    )  # 17 Nov 00:00 local: yesterday
    items = await reminders.compute(db_session, w.client, "Europe/Istanbul", now)
    kinds = {(k.value, a.id) for k, a in items}
    assert kinds == {("prepare_summary", late.id), ("after_session_note", yesterday.id)}
    assert early_next.id not in {a.id for _, a in items}


# --- Export ------------------------------------------------------------------------------


async def _populate(db: AsyncSession, w: World, client: User) -> dict[str, uuid.UUID]:
    """One row in every table that holds the client's data."""
    entry = Entry(
        organization_id=client.organization_id,
        client_id=client.id,
        kind=EntryKind.QUICK,
        occurred_at=datetime.now(UTC) - timedelta(hours=1),
        note=f"günlük-{client.display_name}",
        details={"mood": 3},
    )
    appointment = await _appointment(db, w, client, _local_noon(1))
    summary = await _summary(
        db,
        client,
        SummaryStatus.SHARED,
        topics=[f"konu-{client.display_name}"],
        appointment_id=appointment.id,
    )
    statement = SummaryStatement(
        summary_id=summary.id, position=0, section="G", text=f"ifade-{client.display_name}"
    )
    db.add_all([entry, statement])
    await db.flush()
    db.add_all(
        [
            SummaryCitation(statement_id=statement.id, entry_id=entry.id),
            AfterSessionNote(
                organization_id=client.organization_id,
                client_id=client.id,
                source_text=f"seans-{client.display_name}",
            ),
            SupportPlan(
                organization_id=client.organization_id,
                client_id=client.id,
                self_note=f"plan-{client.display_name}",
            ),
            SummaryJob(
                organization_id=client.organization_id,
                client_id=client.id,
                period_start=datetime.now(UTC).date(),
                period_end=datetime.now(UTC).date(),
                appointment_id=appointment.id,
            ),
            LlmUsage(
                organization_id=client.organization_id,
                user_id=client.id,
                purpose="summary",
                model="m",
                input_tokens=1,
                output_tokens=1,
                requests=1,
                cost_usd=Decimal("0.01"),
                duration_ms=1,
                success=True,
            ),
            Invitation(
                organization_id=client.organization_id,
                invited_by_id=w.clin.id if client.organization_id == w.org_a.id else w.clin_b.id,
                email=client.email,
                role=UserRole.CLIENT,
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=datetime.now(UTC),
            ),
            RefreshToken(
                jti=uuid.uuid4().hex,
                family_id=uuid.uuid4(),
                user_id=client.id,
                family_started_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            ),
        ]
    )
    await db.flush()
    return {"summary": summary.id, "entry": entry.id}


async def test_export_contains_only_own_data(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    await _populate(db_session, w, w.client)
    await _populate(db_session, w, w.client2)
    await _populate(db_session, w, w.client_b)
    acting.user = w.client
    r = await http.get(f"{API}/account/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["email"] == w.client.email
    assert set(data) == {
        "exported_at",
        "profile",
        "entries",
        "summaries",
        "after_session_notes",
        "plan",
        "appointments",
    }
    assert len(data["entries"]) == len(data["summaries"]) == len(data["appointments"]) == 1
    assert len(data["after_session_notes"]) == 1
    assert data["summaries"][0]["topics"] == ["konu-client"]
    assert data["summaries"][0]["statements"][0]["source_entry_ids"] == [data["entries"][0]["id"]]
    assert data["plan"]["self_note"] == "plan-client"
    assert data["after_session_notes"][0]["source_text"] == "seans-client"
    raw = r.text
    for other in ("client2", "client-b", w.client2.email, w.client_b.email):
        assert other not in raw
    assert str(w.client2.id) not in raw and str(w.client_b.id) not in raw
    event = await db_session.scalar(select(AuditLog).where(AuditLog.action == "account.export"))
    assert event is not None and event.actor_id == w.client.id and event.detail == {}


async def test_export_without_data_and_role_restrictions(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.client2
    data = (await http.get(f"{API}/account/export")).json()
    assert data["entries"] == [] and data["plan"] is None
    for user in (w.clin, w.admin):
        acting.user = user
        assert (await http.get(f"{API}/account/export")).status_code == 403
    acting.user = None
    assert (await http.get(f"{API}/account/export")).status_code == 401


async def test_export_is_rate_limited(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.client
    codes = [(await http.get(f"{API}/account/export")).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


# --- Account deletion --------------------------------------------------------------------

DELETE_TABLES = {
    User: User.id,
    Entry: Entry.client_id,
    Appointment: Appointment.client_id,
    Summary: Summary.client_id,
    SummaryJob: SummaryJob.client_id,
    AfterSessionNote: AfterSessionNote.client_id,
    SupportPlan: SupportPlan.client_id,
    CareAssignment: CareAssignment.client_id,
    RefreshToken: RefreshToken.user_id,
    LlmUsage: LlmUsage.user_id,
}


async def _counts(db: AsyncSession, client: User) -> dict[str, int]:
    out = {
        model.__name__: await db.scalar(select(func.count()).where(col == client.id))
        for model, col in DELETE_TABLES.items()
    }
    out["SummaryStatement"] = await db.scalar(
        select(func.count(SummaryStatement.id))
        .join(Summary, Summary.id == SummaryStatement.summary_id)
        .where(Summary.client_id == client.id)
    )
    out["Invitation"] = await db.scalar(
        select(func.count()).select_from(Invitation).where(Invitation.email == client.email)
    )
    return out


def _body(**kw: str) -> dict[str, str]:
    return {"password": TEST_PASSWORD, "confirmation": "SİL", **kw}


async def test_delete_requires_confirmation_and_correct_password(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    await _populate(db_session, w, w.client)
    acting.user = w.client
    bad = [
        {"password": TEST_PASSWORD},
        {"confirmation": "SİL"},
        {"password": TEST_PASSWORD, "confirmation": "sil"},
    ]
    for body in bad:
        assert (await http.request("DELETE", f"{API}/account", json=body)).status_code == 422
    r = await http.request("DELETE", f"{API}/account", json=_body(password="wrong-password-123"))
    assert r.status_code == 403
    assert await db_session.get(User, w.client.id) is not None
    assert all(v >= 1 for k, v in (await _counts(db_session, w.client)).items())


async def test_delete_removes_every_row_of_the_client_and_nothing_else(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    await _populate(db_session, w, w.client)
    await _populate(db_session, w, w.client2)
    await _populate(db_session, w, w.client_b)
    before_other = {
        w.client2.id: await _counts(db_session, w.client2),
        w.client_b.id: await _counts(db_session, w.client_b),
    }
    before_staff = await db_session.scalar(
        select(func.count(User.id)).where(User.role != UserRole.CLIENT)
    )
    before_citations = await db_session.scalar(select(func.count()).select_from(SummaryCitation))
    assert all(v >= 1 for v in (await _counts(db_session, w.client)).values())

    acting.user = w.client
    token_header = dict(http.headers)
    r = await http.request("DELETE", f"{API}/account", json=_body())
    assert r.status_code == 204

    assert all(v == 0 for v in (await _counts(db_session, w.client)).values())
    assert await db_session.scalar(select(func.count()).select_from(SummaryCitation)) == (
        before_citations - 1
    )
    assert await _counts(db_session, w.client2) == before_other[w.client2.id]
    assert await _counts(db_session, w.client_b) == before_other[w.client_b.id]
    assert before_staff == await db_session.scalar(
        select(func.count(User.id)).where(User.role != UserRole.CLIENT)
    )
    assert await db_session.get(Organization, w.org_a.id) is not None

    # The old access token no longer works.
    assert http.headers["Authorization"] == token_header["authorization"]
    assert (await http.get(f"{API}/auth/me")).status_code == 401
    assert (await http.get(f"{API}/summaries")).status_code == 401

    # The clinician no longer sees the shared summary; the other client's stays visible.
    acting.user = w.clin
    shared = (await http.get(f"{API}/clinician/summaries")).json()
    assert len(shared) == 1
    clients = (await http.get(f"{API}/clinician/clients")).json()
    assert [c["id"] for c in clients] == [str(w.client2.id)]


async def test_delete_audit_event_has_no_content(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    await _populate(db_session, w, w.client)
    acting.user = w.client
    assert (await http.request("DELETE", f"{API}/account", json=_body())).status_code == 204
    event = await db_session.scalar(select(AuditLog).where(AuditLog.action == "account.delete"))
    assert event is not None
    assert event.actor_id == w.client.id and event.organization_id == w.org_a.id
    assert event.detail == {} and event.target_id is None
    assert w.client.email not in json.dumps(
        [e.detail for e in (await db_session.scalars(select(AuditLog))).all()]
    )


async def test_delete_is_client_only_and_never_for_someone_else(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    for user in (w.clin, w.admin):
        acting.user = user
        assert (await http.request("DELETE", f"{API}/account", json=_body())).status_code == 403
        assert await db_session.get(User, user.id) is not None
    acting.user = None
    assert (await http.request("DELETE", f"{API}/account", json=_body())).status_code == 401
    # There is no way to name another account; a client's request only ever touches themself.
    acting.user = w.client2
    r = await http.request(
        "DELETE", f"{API}/account", json={**_body(), "client_id": str(w.client.id)}
    )
    assert r.status_code == 204
    assert await db_session.get(User, w.client.id) is not None
    assert await db_session.get(User, w.client2.id) is None


async def test_delete_wrong_password_attempts_are_rate_limited(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.client
    codes = [
        (
            await http.request("DELETE", f"{API}/account", json=_body(password="nope-nope-nope"))
        ).status_code
        for _ in range(6)
    ]
    assert codes == [403] * 5 + [429]


async def test_deleted_users_refresh_tokens_cannot_be_used(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    login = await http.post(
        f"{API}/auth/login", json={"email": w.client.email, "password": TEST_PASSWORD}
    )
    refresh = login.json()["refresh_token"]
    acting.user = w.client
    assert (await http.request("DELETE", f"{API}/account", json=_body())).status_code == 204
    assert (
        await http.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    ).status_code == 401
    assert await db_session.scalar(text("select count(*) from refresh_tokens where false")) == 0
