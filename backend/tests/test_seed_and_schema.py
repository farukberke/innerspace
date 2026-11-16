"""Seed script and migration consistency."""

from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.models import Appointment, Entry, EntryKind, Organization, User, UserRole
from app.seed import ORGS, seed


async def test_seed_is_idempotent_and_consistent(db_session: AsyncSession) -> None:
    assert await seed(db_session, password="seed-password-123") == [o.slug for o in ORGS]
    assert await seed(db_session, password="seed-password-123") == []

    assert await db_session.scalar(select(func.count(Organization.id))) == len(ORGS)
    assert await db_session.scalar(select(func.count(User.id))) == sum(len(o.users) for o in ORGS)
    assert await db_session.scalar(select(func.count(Entry.id))) > 0

    # Every entry/appointment belongs to a client of the same organization.
    mismatched = await db_session.scalar(
        select(func.count(Entry.id))
        .join(User, User.id == Entry.client_id)
        .where((User.organization_id != Entry.organization_id) | (User.role != UserRole.CLIENT))
    )
    assert mismatched == 0
    assert await db_session.scalar(select(func.count(Appointment.id))) > 0


def test_models_match_migrations(alembic_config: Config, migrated_db: None) -> None:
    command.check(alembic_config)  # raises if autogenerate would detect changes


async def test_entry_owner_must_belong_to_entry_organization(db_session: AsyncSession) -> None:
    """Database-level guard: composite FK (client_id, organization_id) -> users."""
    await seed(db_session, password="seed-password-123")
    client = await db_session.scalar(
        select(User).where(User.email == "client.emre@other-clinic.test")
    )
    demo_org = await db_session.scalar(
        select(Organization).where(Organization.slug == "demo-clinic")
    )
    assert client is not None and demo_org is not None
    db_session.add(
        Entry(
            organization_id=demo_org.id,
            client_id=client.id,
            kind=EntryKind.QUICK,
            occurred_at=datetime.now(UTC),
            note="x",
            details={},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
