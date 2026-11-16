"""Appointments are created, changed and cancelled only by the assigned clinician; the client
only sees them. `org_admin` has no access. Every query is scoped by organization and
ownership/assignment."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, AppointmentKind, CareAssignment, User
from app.services import audit, people
from app.services.errors import NotFoundError

DEFAULT_PERIOD_DAYS = 14
MAX_PERIOD_DAYS = 92

AppointmentRow = tuple[Appointment, str | None]  # appointment, clinician display name


def _with_clinician_name() -> Select[tuple[Appointment, str | None]]:
    return select(Appointment, User.display_name).outerjoin(
        User,
        (User.id == Appointment.clinician_id)
        & (User.organization_id == Appointment.organization_id),
    )


async def _record(
    session: AsyncSession, action: str, actor: User, appointment_id: uuid.UUID
) -> None:
    await audit.record(
        session,
        action,
        organization_id=actor.organization_id,
        actor_id=actor.id,
        target_type="appointment",
        target_id=appointment_id,
    )


# --- Client ----------------------------------------------------------------------------


async def list_own(session: AsyncSession, client: User) -> list[AppointmentRow]:
    query = (
        _with_clinician_name()
        .where(
            Appointment.client_id == client.id,
            Appointment.organization_id == client.organization_id,
        )
        .order_by(Appointment.scheduled_at.desc(), Appointment.id)
    )
    return [(a, name) for a, name in (await session.execute(query)).all()]


async def get_own(session: AsyncSession, client: User, appointment_id: uuid.UUID) -> Appointment:
    appointment = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.client_id == client.id,
            Appointment.organization_id == client.organization_id,
        )
    )
    if appointment is None:
        raise NotFoundError
    return appointment


# --- Clinician -------------------------------------------------------------------------


async def list_for_client(
    session: AsyncSession, clinician: User, client_id: uuid.UUID
) -> list[AppointmentRow]:
    """All appointments of an assigned client."""
    await people.get_assigned_client(session, clinician, client_id)
    query = (
        _with_clinician_name()
        .where(
            Appointment.client_id == client_id,
            Appointment.organization_id == clinician.organization_id,
        )
        .order_by(Appointment.scheduled_at.desc(), Appointment.id)
    )
    return [(a, name) for a, name in (await session.execute(query)).all()]


async def next_for_clients(
    session: AsyncSession, clinician: User, client_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """Each client's next appointment with this clinician."""
    if not client_ids:
        return {}
    query = (
        select(Appointment.client_id, func.min(Appointment.scheduled_at))
        .where(
            Appointment.organization_id == clinician.organization_id,
            Appointment.clinician_id == clinician.id,
            Appointment.client_id.in_(client_ids),
            Appointment.scheduled_at >= datetime.now(UTC),
        )
        .group_by(Appointment.client_id)
    )
    return {client_id: at for client_id, at in (await session.execute(query)).all()}


async def create_for_client(
    session: AsyncSession,
    clinician: User,
    client_id: uuid.UUID,
    kind: AppointmentKind,
    scheduled_at: datetime,
) -> Appointment:
    client = await people.get_assigned_client(session, clinician, client_id)
    appointment = Appointment(
        organization_id=clinician.organization_id,
        client_id=client.id,
        clinician_id=clinician.id,
        created_by_id=clinician.id,
        kind=kind,
        scheduled_at=scheduled_at,
    )
    session.add(appointment)
    await session.flush()
    await _record(session, "appointment.create", clinician, appointment.id)
    await session.commit()
    return appointment


async def _get_managed(
    session: AsyncSession, clinician: User, appointment_id: uuid.UUID
) -> Appointment:
    """An appointment of this clinician for a client still assigned to them."""
    appointment = await session.scalar(
        select(Appointment)
        .join(
            CareAssignment,
            (CareAssignment.client_id == Appointment.client_id)
            & (CareAssignment.organization_id == Appointment.organization_id),
        )
        .where(
            Appointment.id == appointment_id,
            Appointment.organization_id == clinician.organization_id,
            CareAssignment.clinician_id == clinician.id,
        )
    )
    if appointment is None:
        raise NotFoundError
    if appointment.clinician_id != clinician.id:
        raise NotFoundError
    return appointment


async def update_for_client(
    session: AsyncSession, clinician: User, appointment_id: uuid.UUID, changes: dict[str, object]
) -> Appointment:
    appointment = await _get_managed(session, clinician, appointment_id)
    for field, value in changes.items():
        setattr(appointment, field, value)
    await _record(session, "appointment.update", clinician, appointment.id)
    await session.commit()
    return appointment


async def delete_for_client(
    session: AsyncSession, clinician: User, appointment_id: uuid.UUID
) -> None:
    appointment = await _get_managed(session, clinician, appointment_id)
    await session.delete(appointment)
    await _record(session, "appointment.delete", clinician, appointment_id)
    await session.commit()


# --- Summary period --------------------------------------------------------------------


async def default_summary_period(
    session: AsyncSession, client: User, appointment_id: uuid.UUID
) -> tuple[date, date]:
    """Period for a summary prepared for an appointment of this client: from the previous
    appointment's date to this one's (14 days back if there is none; at most 92 days).
    Raises NotFoundError for an appointment that is not the client's own."""
    appointment = await get_own(session, client, appointment_id)
    previous = await session.scalar(
        select(func.max(Appointment.scheduled_at)).where(
            Appointment.client_id == client.id,
            Appointment.organization_id == client.organization_id,
            Appointment.scheduled_at < appointment.scheduled_at,
        )
    )
    end = appointment.scheduled_at.astimezone(UTC).date()
    start = previous.astimezone(UTC).date() if previous else end - timedelta(DEFAULT_PERIOD_DAYS)
    return max(start, end - timedelta(MAX_PERIOD_DAYS)), end
