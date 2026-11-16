"""Seed script and migration consistency."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.models import (
    AfterSessionNote,
    Appointment,
    AuditLog,
    Entry,
    EntryKind,
    LlmUsage,
    Organization,
    Summary,
    SummaryCitation,
    SummaryStatement,
    User,
    UserRole,
)
from app.seed import ORGS, reset_demo, seed


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


async def test_seed_content_is_turkish_and_medication_fictional(db_session: AsyncSession) -> None:
    await seed(db_session, password="seed-password-123")
    org_names = set((await db_session.scalars(select(Organization.name))).all())
    assert org_names == {"Demo Klinik (sentetik)", "Diğer Klinik (sentetik)"}
    meds = (
        await db_session.scalars(select(Entry.details).where(Entry.kind == EntryKind.MEDICATION))
    ).all()
    assert meds and {d["medication_name"] for d in meds} == {"İlaç A (kurgusal)"}
    notes = (await db_session.scalars(select(Entry.note).where(Entry.note.is_not(None)))).all()
    assert notes and not any("Slept" in n or "Episode" in n for n in notes)


async def test_reset_deletes_only_demo_orgs_keeps_audit_and_reseeds(
    db_session: AsyncSession, make_org, make_user
) -> None:
    await seed(db_session, password="seed-password-123")
    other = await make_org("real-clinic")
    outsider = await make_user(other, UserRole.CLIENT, "outsider")

    # Rows in every kind of dependent table of a demo client, including llm_usage, whose
    # foreign key to organizations has no ON DELETE CASCADE.
    ayse = await db_session.scalar(select(User).where(User.email == "client.ayse@demo-clinic.test"))
    assert ayse is not None
    entry = await db_session.scalar(select(Entry).where(Entry.client_id == ayse.id).limit(1))
    assert entry is not None
    summary = Summary(
        organization_id=ayse.organization_id, client_id=ayse.id, title="Özet", body="..."
    )
    db_session.add(summary)
    await db_session.flush()
    statement = SummaryStatement(summary_id=summary.id, position=0, section="Genel", text="x")
    db_session.add(statement)
    await db_session.flush()
    db_session.add_all(
        [
            SummaryCitation(statement_id=statement.id, entry_id=entry.id),
            AfterSessionNote(
                organization_id=ayse.organization_id, client_id=ayse.id, source_text="not"
            ),
            LlmUsage(
                organization_id=ayse.organization_id,
                user_id=ayse.id,
                purpose="summary",
                model="test",
                input_tokens=1,
                output_tokens=1,
                requests=1,
                cost_usd=Decimal("0.01"),
                duration_ms=1,
                success=True,
            ),
        ]
    )
    await db_session.flush()

    assert sorted(await reset_demo(db_session)) == sorted(o.slug for o in ORGS)

    remaining = set((await db_session.scalars(select(Organization.slug))).all())
    assert remaining == {"real-clinic"}
    assert await db_session.get(User, outsider.id) is not None
    for model in (Entry, Summary, SummaryStatement, AfterSessionNote, LlmUsage, Appointment):
        pk = model.__table__.primary_key.columns.values()[0]
        assert await db_session.scalar(select(func.count(pk))) == 0, model.__name__
    resets = await db_session.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.action == "demo_reset")
    )
    assert resets == len(ORGS)

    # Nothing to reset twice; seeding recreates the demo organizations.
    assert await reset_demo(db_session) == []
    assert await seed(db_session, password="seed-password-123") == [o.slug for o in ORGS]
