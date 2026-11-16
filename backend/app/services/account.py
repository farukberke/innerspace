"""The client's data rights: export everything, delete the account. Both act only on the
authenticated client's own data."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import AfterSessionNote, Entry, Invitation, LlmUsage, User, UserRole
from app.schemas.account import AccountExport, ExportAfterSessionNote, ExportProfile
from app.schemas.care import SummaryRead
from app.schemas.entry import EntryRead
from app.schemas.planning import AppointmentRead, PlanRead
from app.services import appointments, audit, plans
from app.services import summaries as summaries_service
from app.services.errors import InvalidCredentialsError


async def export_data(session: AsyncSession, client: User) -> AccountExport:
    entries = await session.scalars(
        select(Entry)
        .where(Entry.client_id == client.id, Entry.organization_id == client.organization_id)
        .order_by(Entry.occurred_at, Entry.id)
    )
    notes = await session.scalars(
        select(AfterSessionNote)
        .where(
            AfterSessionNote.client_id == client.id,
            AfterSessionNote.organization_id == client.organization_id,
        )
        .order_by(AfterSessionNote.created_at, AfterSessionNote.id)
    )
    plan = await plans.get_own(session, client)
    appointment_reads = []
    for appointment, name in await appointments.list_own(session, client):
        read = AppointmentRead.model_validate(appointment)
        read.clinician_name = name
        appointment_reads.append(read)
    export = AccountExport(
        exported_at=datetime.now(UTC),
        profile=ExportProfile.model_validate(client),
        entries=[EntryRead.model_validate(e) for e in entries],
        summaries=[
            SummaryRead.from_model(s) for s in await summaries_service.list_own(session, client)
        ],
        after_session_notes=[ExportAfterSessionNote.model_validate(n) for n in notes],
        plan=PlanRead.model_validate(plan) if plan else None,
        appointments=appointment_reads,
    )
    await audit.record(
        session, "account.export", organization_id=client.organization_id, actor_id=client.id
    )
    await session.commit()
    return export


async def delete_account(session: AsyncSession, client: User, password: str) -> None:
    """Permanently deletes the client and everything of theirs (entries, summaries with
    statements and citations, notes, plan, appointments, assignments, refresh tokens: all by
    ON DELETE CASCADE). Clinicians lose access with the rows. Only the content-free audit
    event remains (the audit log has no foreign keys)."""
    if client.role != UserRole.CLIENT:  # defence in depth; the route already requires it
        raise InvalidCredentialsError
    if not await verify_password(password, client.password_hash):
        raise InvalidCredentialsError
    organization_id, user_id, email = client.organization_id, client.id, client.email
    await audit.record(session, "account.delete", organization_id=organization_id, actor_id=user_id)
    # Rows without a cascading foreign key that still refer to the person.
    await session.execute(delete(LlmUsage).where(LlmUsage.user_id == user_id))
    await session.execute(
        delete(Invitation).where(
            Invitation.organization_id == organization_id, Invitation.email == email
        )
    )
    await session.execute(
        delete(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    await session.commit()
