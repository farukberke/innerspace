"""Appointments and the support plan ("Planım"): ownership, assignment, sharing, organization
isolation, org_admin exclusion, summary-appointment link, crisis contacts."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    AppointmentKind,
    AuditLog,
    CareAssignment,
    Entry,
    EntryKind,
    Organization,
    Summary,
    SupportPlan,
    User,
    UserRole,
)
from app.services import jobs
from tests.test_ai import Script, draft

API = "/api/v1"
SOON = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0)


@dataclass
class World:
    org_a: Organization
    admin: User
    clin: User
    clin2: User  # same org, not assigned to `client`
    client: User
    client2: User  # same org, assigned to clin2
    clin_b: User
    client_b: User  # other org
    assignment: CareAssignment


@pytest.fixture
async def w(make_org, make_user, db_session: AsyncSession, org_a, org_b) -> World:
    clin = await make_user(org_a, UserRole.CLINICIAN, "clin")
    clin2 = await make_user(org_a, UserRole.CLINICIAN, "clin2")
    client = await make_user(org_a, UserRole.CLIENT, "client")
    client2 = await make_user(org_a, UserRole.CLIENT, "client2")
    assignment = CareAssignment(
        organization_id=org_a.id,
        clinician_id=clin.id,
        client_id=client.id,
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add_all(
        [
            assignment,
            CareAssignment(organization_id=org_a.id, clinician_id=clin2.id, client_id=client2.id),
        ]
    )
    await db_session.flush()
    return World(
        org_a=org_a,
        admin=await make_user(org_a, UserRole.ORG_ADMIN, "admin"),
        clin=clin,
        clin2=clin2,
        client=client,
        client2=client2,
        clin_b=await make_user(org_b, UserRole.CLINICIAN, "clin-b"),
        client_b=await make_user(org_b, UserRole.CLIENT, "client-b"),
        assignment=assignment,
    )


def body(**kw: Any) -> dict[str, Any]:
    return {"kind": "therapy", "scheduled_at": SOON.isoformat(), **kw}


async def _clinic(http: AsyncClient, acting, w: World, **kw: Any) -> dict[str, Any]:
    acting.user = w.clin
    response = await http.post(
        f"{API}/clinician/clients/{w.client.id}/appointments", json=body(**kw)
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Appointments: clinician -----------------------------------------------------------


async def test_clinician_manages_appointments_of_assigned_client(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    created = await _clinic(http, acting, w)
    assert created["clinician_id"] == str(w.clin.id)
    assert created["clinician_name"] == w.clin.display_name

    later = (SOON + timedelta(days=1)).isoformat()
    patched = await http.patch(
        f"{API}/clinician/appointments/{created['id']}",
        json={"scheduled_at": later, "kind": "psychiatry"},
    )
    assert patched.status_code == 200
    assert patched.json()["kind"] == "psychiatry"

    listed = (await http.get(f"{API}/clinician/clients/{w.client.id}/appointments")).json()
    assert [a["id"] for a in listed] == [created["id"]]
    assert (await http.delete(f"{API}/clinician/appointments/{created['id']}")).status_code == 204
    assert (await http.get(f"{API}/clinician/clients/{w.client.id}/appointments")).json() == []
    actions = list(await db_session.scalars(select(AuditLog.action)))
    assert {"appointment.create", "appointment.update", "appointment.delete"} <= set(actions)


async def test_clinician_cannot_touch_unassigned_or_foreign_clients(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.clin
    for client in (w.client2, w.client_b):
        url = f"{API}/clinician/clients/{client.id}/appointments"
        assert (await http.post(url, json=body())).status_code == 404
        assert (await http.get(url)).status_code == 404
    # An appointment of someone else's client cannot be changed or deleted either.
    other = await _clinic_for(http, acting, w.clin2, w.client2)
    acting.user = w.clin
    for call in (
        http.patch(f"{API}/clinician/appointments/{other}", json={"kind": "therapy"}),
        http.delete(f"{API}/clinician/appointments/{other}"),
    ):
        assert (await call).status_code == 404


async def _clinic_for(http: AsyncClient, acting, clinician: User, client: User) -> str:
    acting.user = clinician
    response = await http.post(f"{API}/clinician/clients/{client.id}/appointments", json=body())
    assert response.status_code == 201
    return response.json()["id"]


async def test_clinician_loses_access_when_assignment_is_removed(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    created = await _clinic(http, acting, w)
    await db_session.delete(w.assignment)
    await db_session.flush()
    assert (
        await http.patch(f"{API}/clinician/appointments/{created['id']}", json={"kind": "therapy"})
    ).status_code == 404
    assert (
        await http.get(f"{API}/clinician/clients/{w.client.id}/appointments")
    ).status_code == 404


async def test_clinician_cannot_change_another_clinicians_appointment(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    # `client` is assigned to both clinicians; clin2's appointment is not clin's to manage.
    db_session.add(
        CareAssignment(
            organization_id=w.org_a.id,
            clinician_id=w.clin2.id,
            client_id=w.client.id,
        )
    )
    await db_session.flush()
    theirs = await _clinic_for(http, acting, w.clin2, w.client)
    acting.user = w.clin
    assert (
        await http.patch(f"{API}/clinician/appointments/{theirs}", json={"kind": "therapy"})
    ).status_code == 404
    assert (await http.delete(f"{API}/clinician/appointments/{theirs}")).status_code == 404


async def test_appointment_validation(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.clin
    url = f"{API}/clinician/clients/{w.client.id}/appointments"
    assert (await http.post(url, json=body(kind="surgery"))).status_code == 422
    assert (await http.post(url, json=body(scheduled_at="2026-12-01T10:00:00"))).status_code == 422
    assert (await http.post(url, json={"kind": "therapy"})).status_code == 422
    created = await _clinic(http, acting, w)
    path = f"{API}/clinician/appointments/{created['id']}"
    assert (await http.patch(path, json={"kind": None})).status_code == 200  # no-op, not cleared
    assert (await http.get(url)).json()[0]["kind"] == "therapy"


# --- Appointments: client --------------------------------------------------------------


async def test_client_sees_appointments_but_cannot_create_change_or_delete_them(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    clinic = await _clinic(http, acting, w)
    acting.user = w.client
    listed = (await http.get(f"{API}/appointments")).json()
    assert [a["id"] for a in listed] == [clinic["id"]]
    assert listed[0]["clinician_name"] == w.clin.display_name
    # No client-side write endpoints exist, and the clinician ones are closed to clients.
    assert (await http.post(f"{API}/appointments", json=body())).status_code in (404, 405)
    for call in (
        http.patch(f"{API}/appointments/{clinic['id']}", json={"kind": "psychiatry"}),
        http.delete(f"{API}/appointments/{clinic['id']}"),
        http.patch(f"{API}/clinician/appointments/{clinic['id']}", json={"kind": "psychiatry"}),
        http.delete(f"{API}/clinician/appointments/{clinic['id']}"),
        http.post(f"{API}/clinician/clients/{w.client.id}/appointments", json=body()),
    ):
        assert (await call).status_code in (403, 404, 405)
    after = (await http.get(f"{API}/appointments")).json()
    assert after == listed
    assert await db_session.scalar(select(func.count()).select_from(Appointment)) == 1


async def test_client_cannot_see_other_clients_appointments(
    http: AsyncClient, acting, w: World
) -> None:
    mine = await _clinic(http, acting, w)
    theirs = await _clinic_for(http, acting, w.clin2, w.client2)
    assert theirs != mine["id"]
    acting.user = w.client
    assert [a["id"] for a in (await http.get(f"{API}/appointments")).json()] == [mine["id"]]
    acting.user = w.client_b
    assert (await http.get(f"{API}/appointments")).json() == []


async def test_clinician_client_list_shows_next_clinic_appointment(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.clin
    assert (await http.get(f"{API}/clinician/clients")).json()[0]["next_appointment_at"] is None
    past = Appointment(
        organization_id=w.org_a.id,
        client_id=w.client.id,
        clinician_id=w.clin.id,
        kind=AppointmentKind.THERAPY,
        scheduled_at=datetime.now(UTC) - timedelta(days=2),
    )
    db_session.add(past)
    await db_session.flush()
    first = await _clinic(http, acting, w)
    await _clinic(http, acting, w, scheduled_at=(SOON + timedelta(days=9)).isoformat())
    listed = (await http.get(f"{API}/clinician/clients")).json()
    assert datetime.fromisoformat(listed[0]["next_appointment_at"]) == datetime.fromisoformat(
        first["scheduled_at"]
    )


# --- org_admin and roles ---------------------------------------------------------------


async def test_org_admin_has_no_access_to_appointments_or_plans(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.admin
    fake = "00000000-0000-0000-0000-000000000001"
    calls = [
        http.get(f"{API}/appointments"),
        http.get(f"{API}/clinician/clients/{w.client.id}/appointments"),
        http.post(f"{API}/clinician/clients/{w.client.id}/appointments", json=body()),
        http.patch(f"{API}/clinician/appointments/{fake}", json={}),
        http.delete(f"{API}/clinician/appointments/{fake}"),
        http.get(f"{API}/plan"),
        http.put(f"{API}/plan", json={}),
        http.post(f"{API}/plan/share"),
        http.post(f"{API}/plan/unshare"),
        http.get(f"{API}/clinician/clients/{w.client.id}/plan"),
    ]
    for call in calls:
        assert (await call).status_code == 403


async def test_roles_are_separated_and_auth_required(http: AsyncClient, acting, w: World) -> None:
    assert (await http.get(f"{API}/appointments")).status_code == 401
    assert (await http.get(f"{API}/plan")).status_code == 401
    acting.user = w.clin
    assert (await http.get(f"{API}/appointments")).status_code == 403
    assert (await http.get(f"{API}/plan")).status_code == 403
    acting.user = w.client
    assert (await http.get(f"{API}/clinician/clients/{w.client.id}/plan")).status_code == 403
    assert (
        await http.post(f"{API}/clinician/clients/{w.client.id}/appointments", json=body())
    ).status_code == 403


# --- Support plan ----------------------------------------------------------------------

PLAN = {
    "moment_steps": ["Nefes al", "Birini ara"],
    "self_note": "Geçecek.",
    "contacts": [{"name": "Ablam", "phone": "0555 000 00 01"}],
    "warning_signs": ["Uykusuzluk"],
    "coping_strategies": ["Yürüyüş"],
    "talk_to_clinician": ["Atak"],
}


async def test_client_creates_and_updates_own_plan(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.client
    empty = (await http.get(f"{API}/plan")).json()
    assert empty["moment_steps"] == [] and empty["shared_at"] is None
    saved = await http.put(f"{API}/plan", json=PLAN)
    assert saved.status_code == 200 and saved.json()["contacts"] == PLAN["contacts"]
    again = await http.put(f"{API}/plan", json={**PLAN, "self_note": "Yeni"})
    assert again.json()["self_note"] == "Yeni"
    assert (await http.get(f"{API}/plan")).json()["moment_steps"] == PLAN["moment_steps"]
    plans = list(await db_session.scalars(select(SupportPlan)))
    assert len(plans) == 1 and plans[0].client_id == w.client.id
    logged = list(
        await db_session.scalars(select(AuditLog).where(AuditLog.action == "plan.update"))
    )
    assert len(logged) == 2 and "Yeni" not in str([log.detail for log in logged])


@pytest.mark.parametrize(
    "patch",
    [
        {"moment_steps": ["x"] * 11},
        {"moment_steps": ["y" * 201]},
        {"moment_steps": [" "]},
        {"self_note": "z" * 501},
        {"contacts": [{"name": "A", "phone": "0555"}] * 9},
        {"contacts": [{"name": "", "phone": "0555 000 00 01"}]},
        {"contacts": [{"name": "A", "phone": "javascript:alert(1)"}]},
        {"contacts": [{"name": "A", "phone": "12"}]},
        {"warning_signs": "not a list"},
    ],
)
async def test_plan_validation(http: AsyncClient, acting, w: World, patch: dict[str, Any]) -> None:
    acting.user = w.client
    assert (await http.put(f"{API}/plan", json={**PLAN, **patch})).status_code == 422


async def test_plans_are_per_client_private(http: AsyncClient, acting, w: World) -> None:
    acting.user = w.client
    await http.put(f"{API}/plan", json=PLAN)
    acting.user = w.client2
    assert (await http.get(f"{API}/plan")).json()["moment_steps"] == []
    acting.user = w.client_b
    assert (await http.get(f"{API}/plan")).json()["moment_steps"] == []


async def test_clinician_sees_plan_only_while_shared(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    url = f"{API}/clinician/clients/{w.client.id}/plan"
    acting.user = w.client
    assert (await http.post(f"{API}/plan/share")).status_code == 404  # no plan yet
    await http.put(f"{API}/plan", json=PLAN)
    acting.user = w.clin
    assert (await http.get(url)).status_code == 404  # created but private

    acting.user = w.client
    shared = await http.post(f"{API}/plan/share")
    assert shared.status_code == 200 and shared.json()["shared_at"] is not None
    acting.user = w.clin
    seen = await http.get(url)
    assert seen.status_code == 200 and seen.json()["contacts"] == PLAN["contacts"]
    assert "id" not in seen.json() and "client_id" not in seen.json()
    view = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "plan.view"))).one()
    assert view.actor_id == w.clin.id and "Ablam" not in str(view.detail)

    acting.user = w.client
    assert (await http.post(f"{API}/plan/unshare")).json()["shared_at"] is None
    assert (await http.post(f"{API}/plan/unshare")).status_code == 200  # idempotent
    acting.user = w.clin
    assert (await http.get(url)).status_code == 404


async def test_shared_plan_access_ends_with_assignment_and_is_not_inherited(
    http: AsyncClient, acting, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.client
    await http.put(f"{API}/plan", json=PLAN)
    await http.post(f"{API}/plan/share")
    url = f"{API}/clinician/clients/{w.client.id}/plan"

    # Another clinician of the same org, never assigned: no access.
    acting.user = w.clin2
    assert (await http.get(url)).status_code == 404
    # Assigned only after the sharing happened: no access until the client shares again.
    db_session.add(
        CareAssignment(
            organization_id=w.org_a.id,
            clinician_id=w.clin2.id,
            client_id=w.client.id,
            created_at=datetime.now(UTC) + timedelta(seconds=5),
        )
    )
    await db_session.flush()
    assert (await http.get(url)).status_code == 404
    acting.user = w.client
    await http.post(f"{API}/plan/share")  # renews shared_at
    plan = await db_session.scalar(select(SupportPlan))
    plan.shared_at = datetime.now(UTC) + timedelta(seconds=10)
    await db_session.flush()
    acting.user = w.clin2
    assert (await http.get(url)).status_code == 200

    # Removing the original assignment ends that clinician's access.
    acting.user = w.clin
    assert (await http.get(url)).status_code == 200
    await db_session.delete(w.assignment)
    await db_session.flush()
    assert (await http.get(url)).status_code == 404


async def test_other_organization_cannot_see_plan_or_appointments(
    http: AsyncClient, acting, w: World
) -> None:
    acting.user = w.client
    await http.put(f"{API}/plan", json=PLAN)
    await http.post(f"{API}/plan/share")
    acting.user = w.clin_b
    assert (await http.get(f"{API}/clinician/clients/{w.client.id}/plan")).status_code == 404
    assert (
        await http.get(f"{API}/clinician/clients/{w.client.id}/appointments")
    ).status_code == 404
    assert (await http.get(f"{API}/clinician/clients")).json() == []


# --- Summary <-> appointment -----------------------------------------------------------


def _entry(w: World, when: datetime) -> Entry:
    return Entry(
        organization_id=w.org_a.id,
        client_id=w.client.id,
        kind=EntryKind.QUICK,
        occurred_at=when,
        note="Sakin bir gün.",
        details={"mood": 3},
    )


async def test_generate_with_appointment_uses_previous_appointment_as_period_start(
    http: AsyncClient, acting, llm, w: World, db_session: AsyncSession
) -> None:
    previous = datetime(2026, 11, 3, 14, tzinfo=UTC)
    upcoming = datetime(2026, 11, 17, 14, tzinfo=UTC)
    prev_appt, appt = (
        Appointment(
            organization_id=w.org_a.id,
            client_id=w.client.id,
            clinician_id=w.clin.id,
            kind=AppointmentKind.THERAPY,
            scheduled_at=at,
        )
        for at in (previous, upcoming)
    )
    entry = _entry(w, datetime(2026, 11, 10, 12, tzinfo=UTC))
    db_session.add_all([prev_appt, appt, entry])
    await db_session.flush()

    script = Script(draft(entry.id))
    llm.model = script.model
    acting.llm = llm
    acting.user = w.client
    response = await http.post(f"{API}/summaries/generate", json={"appointment_id": str(appt.id)})
    assert response.status_code == 202
    job = response.json()
    assert (job["period_start"], job["period_end"]) == ("2026-11-03", "2026-11-17")
    assert job["appointment_id"] == str(appt.id)

    await jobs.run(db_session, acting.settings, llm.model, acting.jobq.ids[0], final_attempt=False)
    summary = await db_session.scalar(select(Summary))
    assert summary is not None and summary.appointment_id == appt.id
    read = (await http.get(f"{API}/summaries/{summary.id}")).json()
    assert read["appointment_id"] == str(appt.id)
    assert (read["period_start"], read["period_end"]) == ("2026-11-03", "2026-11-17")


async def test_generate_with_first_appointment_defaults_to_14_days_and_explicit_period_wins(
    http: AsyncClient, acting, llm, w: World, db_session: AsyncSession
) -> None:
    appt = Appointment(
        organization_id=w.org_a.id,
        client_id=w.client.id,
        clinician_id=w.clin.id,
        kind=AppointmentKind.THERAPY,
        scheduled_at=datetime(2026, 11, 17, 14, tzinfo=UTC),
    )
    db_session.add(appt)
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.llm = llm
    acting.user = w.client
    first = (
        await http.post(f"{API}/summaries/generate", json={"appointment_id": str(appt.id)})
    ).json()
    assert first["period_start"] == "2026-11-03" and first["period_end"] == "2026-11-17"
    explicit = (
        await http.post(
            f"{API}/summaries/generate",
            json={
                "appointment_id": str(appt.id),
                "period_start": "2026-11-10",
                "period_end": "2026-11-17",
            },
        )
    ).json()
    assert explicit["period_start"] == "2026-11-10"


async def test_generate_cannot_link_someone_elses_appointment(
    http: AsyncClient, acting, llm, w: World, db_session: AsyncSession
) -> None:
    foreign = Appointment(
        organization_id=w.client_b.organization_id,
        client_id=w.client_b.id,
        clinician_id=w.clin_b.id,
        kind=AppointmentKind.THERAPY,
        scheduled_at=SOON,
    )
    same_org = Appointment(
        organization_id=w.org_a.id,
        client_id=w.client2.id,
        clinician_id=w.clin2.id,
        kind=AppointmentKind.THERAPY,
        scheduled_at=SOON,
    )
    db_session.add_all([foreign, same_org])
    await db_session.flush()
    llm.model = Script(draft()).model
    acting.llm = llm
    acting.user = w.client
    for appt in (foreign, same_org):
        response = await http.post(
            f"{API}/summaries/generate", json={"appointment_id": str(appt.id)}
        )
        assert response.status_code == 404
    assert acting.jobq.ids == []


async def test_generate_requires_period_or_appointment(
    http: AsyncClient, acting, llm, w: World
) -> None:
    llm.model = Script(draft()).model
    acting.llm = llm
    acting.user = w.client
    assert (await http.post(f"{API}/summaries/generate", json={})).status_code == 422
    half = {"period_start": "2026-11-01"}
    assert (await http.post(f"{API}/summaries/generate", json=half)).status_code == 422


# --- Crisis: plan contacts -------------------------------------------------------------


def _must_not_run(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    raise AssertionError("the LLM must not be called on crisis language")


async def test_crisis_response_carries_only_own_plan_contacts(
    http: AsyncClient, acting, llm, w: World
) -> None:
    from app.ai.crisis import CRISIS_MESSAGE

    llm.model = FunctionModel(_must_not_run)
    acting.user = w.client
    await http.put(f"{API}/plan", json=PLAN)
    acting.user = w.client2
    await http.put(
        f"{API}/plan", json={**PLAN, "contacts": [{"name": "Baska", "phone": "0555 111 11 11"}]}
    )
    acting.user = w.client
    response = await http.post(f"{API}/after-session-notes", json={"text": "I want to die."})
    assert response.status_code == 200
    crisis = response.json()
    assert crisis["crisis"] is True and crisis["message"] == CRISIS_MESSAGE
    assert crisis["contacts"] == PLAN["contacts"]
    assert "Baska" not in response.text

    acting.user = w.client_b  # no plan: contacts empty, message unchanged
    other = (await http.post(f"{API}/after-session-notes", json={"text": "I want to die."})).json()
    assert other["contacts"] == [] and other["message"] == CRISIS_MESSAGE


async def test_crisis_job_result_carries_plan_contacts(
    http: AsyncClient, acting, llm, w: World, db_session: AsyncSession
) -> None:
    acting.user = w.client
    await http.put(f"{API}/plan", json=PLAN)
    entry = _entry(w, datetime(2026, 11, 10, 12, tzinfo=UTC))
    entry.note = "Bazen kendimi öldürmek istiyorum"
    db_session.add(entry)
    await db_session.flush()
    llm.model = FunctionModel(_must_not_run)
    acting.llm = llm
    job = (
        await http.post(
            f"{API}/summaries/generate",
            json={"period_start": "2026-11-01", "period_end": "2026-11-15"},
        )
    ).json()
    await jobs.run(db_session, acting.settings, llm.model, acting.jobq.ids[0], final_attempt=False)
    done = (await http.get(f"{API}/summaries/jobs/{job['id']}")).json()
    assert done["status"] == "crisis" and done["crisis"]["contacts"] == PLAN["contacts"]


# --- Seed and schema -------------------------------------------------------------------


async def test_seed_creates_plans_and_shared_plan(
    db_session: AsyncSession,
) -> None:
    from app.seed import AYSE_EMAIL, ELIF_EMAIL, reset_demo, seed

    await seed(db_session, password="seed-password-123")
    ayse = await db_session.scalar(select(User).where(User.email == AYSE_EMAIL))
    elif_ = await db_session.scalar(select(User).where(User.email == ELIF_EMAIL))
    plans = list(await db_session.scalars(select(SupportPlan)))
    assert len(plans) == 4
    shared = [p for p in plans if p.shared_at is not None]
    assert [p.client_id for p in shared] == [ayse.id]
    assignment = await db_session.scalar(
        select(CareAssignment).where(CareAssignment.client_id == ayse.id)
    )
    assert assignment.clinician_id == elif_.id and shared[0].shared_at >= assignment.created_at
    assert all(a.clinician_id is not None for a in await db_session.scalars(select(Appointment)))

    await reset_demo(db_session)
    assert list(await db_session.scalars(select(SupportPlan))) == []
    assert await seed(db_session, password="seed-password-123")
