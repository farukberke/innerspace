"""Summaries: private to the client until shared; clinicians see only shared ones of clients
assigned to them. Every query is scoped by organization and ownership/assignment."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CareAssignment, Summary, User
from app.services import audit
from app.services.errors import NotFoundError


def _owned_by(client: User) -> Select[tuple[Summary]]:
    return select(Summary).where(
        Summary.client_id == client.id, Summary.organization_id == client.organization_id
    )


def _shared_with(clinician: User) -> Select[tuple[Summary]]:
    return (
        select(Summary)
        .join(
            CareAssignment,
            (CareAssignment.client_id == Summary.client_id)
            & (CareAssignment.organization_id == Summary.organization_id),
        )
        .join(
            User,
            (User.id == Summary.client_id) & (User.organization_id == Summary.organization_id),
        )
        .where(
            User.is_active.is_(True),
            Summary.organization_id == clinician.organization_id,
            CareAssignment.clinician_id == clinician.id,
            Summary.shared_at.is_not(None),
        )
    )


async def create_summary(session: AsyncSession, client: User, title: str, body: str) -> Summary:
    summary = Summary(
        organization_id=client.organization_id, client_id=client.id, title=title, body=body
    )
    session.add(summary)
    await session.commit()
    return summary


async def list_own(session: AsyncSession, client: User) -> list[Summary]:
    query = _owned_by(client).order_by(Summary.created_at.desc(), Summary.id)
    return list((await session.scalars(query)).all())


async def get_own(session: AsyncSession, client: User, summary_id: uuid.UUID) -> Summary:
    summary = await session.scalar(_owned_by(client).where(Summary.id == summary_id))
    if summary is None:
        raise NotFoundError
    return summary


async def set_shared(
    session: AsyncSession, client: User, summary_id: uuid.UUID, shared: bool
) -> Summary:
    """Sharing is the client's explicit approval; unsharing revokes clinician access."""
    summary = await get_own(session, client, summary_id)
    summary.shared_at = datetime.now(UTC) if shared else None
    await audit.record(
        session,
        "summary.share" if shared else "summary.unshare",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="summary",
        target_id=summary.id,
    )
    await session.commit()
    return summary


async def list_shared_with(session: AsyncSession, clinician: User) -> list[Summary]:
    query = _shared_with(clinician).order_by(Summary.shared_at.desc(), Summary.id)
    return list((await session.scalars(query)).all())


async def get_shared_with(session: AsyncSession, clinician: User, summary_id: uuid.UUID) -> Summary:
    summary = await session.scalar(_shared_with(clinician).where(Summary.id == summary_id))
    if summary is None:
        raise NotFoundError
    await audit.record(
        session,
        "summary.view",
        organization_id=clinician.organization_id,
        actor_id=clinician.id,
        target_type="summary",
        target_id=summary.id,
    )
    await session.commit()
    return summary
