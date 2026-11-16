"""The temporary Phase 1 dev-user dependency, the seed script and migration consistency."""

from datetime import UTC, datetime

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.api.deps import get_current_user
from app.core.config import Settings
from app.models import Appointment, Entry, EntryKind, Organization, User, UserRole
from app.seed import ORGS, seed


async def test_dev_user_resolved_by_email(db_session: AsyncSession, test_settings: Settings):
    await seed(db_session)
    settings = test_settings.model_copy(update={"dev_user_email": "client.ayse@demo-clinic.test"})
    user = await get_current_user(db_session, settings)
    assert user.role == UserRole.CLIENT


@pytest.mark.parametrize(
    "update",
    [
        {"dev_user_email": None},
        {"dev_user_email": "nobody@demo-clinic.test"},
        {"dev_user_email": "client.ayse@demo-clinic.test", "app_env": "production"},
    ],
)
async def test_dev_user_unavailable(db_session: AsyncSession, test_settings: Settings, update):
    await seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(db_session, test_settings.model_copy(update=update))
    assert exc.value.status_code == 401


async def test_seed_is_idempotent_and_consistent(db_session: AsyncSession) -> None:
    assert await seed(db_session) == [o.slug for o in ORGS]
    assert await seed(db_session) == []

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
    await seed(db_session)
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
