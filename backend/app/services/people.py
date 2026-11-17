"""Org-admin management of users and clinician-client assignments (no clinical content)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CareAssignment, User, UserRole
from app.services import audit
from app.services.errors import ConflictError, NotFoundError


async def list_users(session: AsyncSession, admin: User, role: UserRole | None) -> list[User]:
    query = select(User).where(User.organization_id == admin.organization_id)
    if role is not None:
        query = query.where(User.role == role)
    return list((await session.scalars(query.order_by(User.display_name, User.id))).all())


async def set_user_active(
    session: AsyncSession,
    admin: User,
    user_id: uuid.UUID,
    active: bool,
) -> User:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.organization_id == admin.organization_id)
    )
    if user is None:
        raise NotFoundError
    if user.id == admin.id:
        raise ConflictError("You cannot change your own status")
    user.is_active = active
    await audit.record(
        session,
        "user.activate" if active else "user.deactivate",
        organization_id=admin.organization_id,
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
    )
    await session.commit()
    return user


async def list_assignments(session: AsyncSession, admin: User) -> list[CareAssignment]:
    query = (
        select(CareAssignment)
        .where(CareAssignment.organization_id == admin.organization_id)
        .order_by(CareAssignment.created_at, CareAssignment.id)
    )
    return list((await session.scalars(query)).all())


async def create_assignment(
    session: AsyncSession, admin: User, clinician_id: uuid.UUID, client_id: uuid.UUID
) -> CareAssignment:
    org_users = select(User.id, User.role).where(
        User.organization_id == admin.organization_id,
        User.id.in_([clinician_id, client_id]),
        User.is_active.is_(True),
    )
    roles = {row.id: row.role for row in await session.execute(org_users)}
    if roles.get(clinician_id) != UserRole.CLINICIAN or roles.get(client_id) != UserRole.CLIENT:
        raise NotFoundError
    duplicate = await session.scalar(
        select(CareAssignment.id).where(
            CareAssignment.clinician_id == clinician_id, CareAssignment.client_id == client_id
        )
    )
    if duplicate is not None:
        raise ConflictError("Assignment already exists")
    assignment = CareAssignment(
        organization_id=admin.organization_id,
        clinician_id=clinician_id,
        client_id=client_id,
        created_at=datetime.now(UTC),
    )
    session.add(assignment)
    try:
        await session.flush()
    except IntegrityError:  # concurrent duplicate
        await session.rollback()
        raise ConflictError("Assignment already exists") from None
    await audit.record(
        session,
        "assignment.create",
        organization_id=admin.organization_id,
        actor_id=admin.id,
        target_type="assignment",
        target_id=assignment.id,
    )
    await session.commit()
    return assignment


async def delete_assignment(
    session: AsyncSession,
    admin: User,
    assignment_id: uuid.UUID,
) -> None:
    assignment = await session.scalar(
        select(CareAssignment).where(
            CareAssignment.id == assignment_id,
            CareAssignment.organization_id == admin.organization_id,
        )
    )
    if assignment is None:
        raise NotFoundError
    await session.delete(assignment)
    await audit.record(
        session,
        "assignment.delete",
        organization_id=admin.organization_id,
        actor_id=admin.id,
        target_type="assignment",
        target_id=assignment_id,
    )
    await session.commit()


async def list_assigned_clients(session: AsyncSession, clinician: User) -> list[User]:
    query = (
        select(User)
        .join(
            CareAssignment,
            (CareAssignment.client_id == User.id)
            & (CareAssignment.organization_id == User.organization_id),
        )
        .where(
            CareAssignment.clinician_id == clinician.id,
            CareAssignment.organization_id == clinician.organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.display_name, User.id)
    )
    return list((await session.scalars(query)).all())


async def get_assigned_client(session: AsyncSession, clinician: User, client_id: uuid.UUID) -> User:
    """The active client, only if assigned to this clinician in the same organization."""
    query = (
        select(User)
        .join(
            CareAssignment,
            (CareAssignment.client_id == User.id)
            & (CareAssignment.organization_id == User.organization_id),
        )
        .where(
            User.id == client_id,
            User.role == UserRole.CLIENT,
            User.is_active.is_(True),
            CareAssignment.clinician_id == clinician.id,
            CareAssignment.organization_id == clinician.organization_id,
        )
    )
    client = await session.scalar(query)
    if client is None:
        raise NotFoundError
    return client
