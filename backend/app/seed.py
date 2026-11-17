"""Synthetic demo data. Everything here is fictional — no real people or health data.

Usage (from `backend/`):  uv run python -m app.seed
Production (demo deployment): SEED_DEMO=1 SEED_PASSWORD=<12+ chars> python -m app.seed
Idempotent: organizations that already exist (by slug) are skipped.
Reset (deletes ONLY the demo organizations below and everything in them, then re-seeds):
    SEED_DEMO=1 SEED_PASSWORD=<12+ chars> python -m app.seed --reset
"""

import argparse
import asyncio
import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.security import hash_password
from app.models import (
    Appointment,
    AppointmentKind,
    AuditLog,
    Base,
    CareAssignment,
    Entry,
    EntryKind,
    Organization,
    Summary,
    SummaryCitation,
    SummaryStatement,
    SummaryStatus,
    SupportPlan,
    User,
    UserRole,
)
from app.services.summaries import render_body


@dataclass(frozen=True)
class SeedUser:
    email: str
    display_name: str
    role: UserRole


@dataclass(frozen=True)
class SeedOrg:
    slug: str
    name: str
    users: tuple[SeedUser, ...]


ORGS: tuple[SeedOrg, ...] = (
    SeedOrg(
        slug="demo-clinic",
        name="Demo Klinik (sentetik)",
        users=(
            SeedUser("admin@demo-clinic.test", "Deniz Yönetici", UserRole.ORG_ADMIN),
            SeedUser("dr.elif@demo-clinic.test", "Dr. Elif Kaya", UserRole.CLINICIAN),
            SeedUser("dr.mert@demo-clinic.test", "Dr. Mert Aydın", UserRole.CLINICIAN),
            SeedUser("client.ayse@demo-clinic.test", "Ayşe Y.", UserRole.CLIENT),
            SeedUser("client.can@demo-clinic.test", "Can D.", UserRole.CLIENT),
            SeedUser("client.zeynep@demo-clinic.test", "Zeynep T.", UserRole.CLIENT),
        ),
    ),
    # A second tenant, used to demonstrate and test organization isolation.
    SeedOrg(
        slug="other-clinic",
        name="Diğer Klinik (sentetik)",
        users=(
            SeedUser("admin@other-clinic.test", "Ozan Yönetici", UserRole.ORG_ADMIN),
            SeedUser("dr.selin@other-clinic.test", "Dr. Selin Er", UserRole.CLINICIAN),
            SeedUser("client.emre@other-clinic.test", "Emre K.", UserRole.CLIENT),
        ),
    ),
)

# Demo content is Turkish, like the UI. Medication names stay obviously fictional.
_QUICK_NOTES = (
    "Kötü uyudum, sabahın çoğunda gergin hissettim.",
    "İşten sonra güzel bir yürüyüş yaptım, ruh halim biraz düzeldi.",
    "Bir iş arkadaşımla tartıştım; kafamda tekrar tekrar düşündüm.",
    "Sakin bir gündü. Nefes egzersizini iki kez denedim.",
    "Bugün kendimi daha çok kendim gibi hissettim.",
)
_PANIC_SYMPTOMS = ("kalp çarpıntısı", "nefes darlığı", "baş dönmesi", "terleme", "titreme")
_PANIC_TRIGGERS = (
    "kalabalık metro",
    "iş toplantısı",
    "belirgin bir tetikleyici yok",
    "market kuyruğu",
)
_AVOIDANCE_SITUATIONS = (
    "metroya binmek",
    "bir arkadaşın doğum günü yemeği",
    "bankayı telefonla aramak",
)


AYSE_EMAIL = "client.ayse@demo-clinic.test"
ELIF_EMAIL = "dr.elif@demo-clinic.test"


def _demo_plan(client: User) -> SupportPlan:
    """A sample support plan (Turkish, fictional phone numbers)."""
    return SupportPlan(
        organization_id=client.organization_id,
        client_id=client.id,
        moment_steps=[
            "Olduğum yerde dur, ayaklarımı yere bastığımı hisset.",
            "4 saniye nefes al, 6 saniye ver; 5 kez tekrarla.",
            "Etrafta gördüğüm 5 şeyi say.",
            "Hazırsam bir kişiyi ara.",
        ],
        self_note="Bu his geçecek. Daha önce de geçti, yine geçecek.",
        contacts=[
            {"name": "Ablam (kurgusal)", "phone": "0555 000 00 01"},
            {"name": "Yakın arkadaşım (kurgusal)", "phone": "0555 000 00 02"},
        ],
        warning_signs=["Uykusuz kalmak", "Göğsümde sıkışma", "İnsanlardan kaçma isteği"],
        coping_strategies=["Kısa bir yürüyüş", "Nefes egzersizi", "Sıcak bir içecek"],
        talk_to_clinician=["Metroda yaşadığım atak", "Uyku düzenim"],
    )


def _entry_payload(rng: random.Random, kind: EntryKind) -> tuple[str | None, dict[str, Any]]:
    match kind:
        case EntryKind.QUICK:
            return rng.choice(_QUICK_NOTES), {"mood": rng.randint(1, 5)}
        case EntryKind.PANIC:
            return "Atak bir süre sonra geçti.", {
                "intensity": rng.randint(4, 9),
                "duration_minutes": rng.choice((5, 10, 15, 25)),
                "symptoms": rng.sample(_PANIC_SYMPTOMS, k=rng.randint(1, 3)),
                "trigger": rng.choice(_PANIC_TRIGGERS),
            }
        case EntryKind.MEDICATION:
            taken = rng.random() > 0.15
            return None, {
                "medication_name": "İlaç A (kurgusal)",
                "taken": taken,
                "side_effects": ["hafif bulantı"] if taken and rng.random() < 0.2 else [],
            }
        case EntryKind.AVOIDANCE:
            return None, {
                "situation": rng.choice(_AVOIDANCE_SITUATIONS),
                "avoided": rng.random() < 0.6,
                "anxiety": rng.randint(3, 9),
            }


def _sleep_hours(rng: random.Random, had_panic: bool) -> float:
    """A plausible night (half-hour steps); nights before an attack skew shorter."""
    low, high = (8, 12) if had_panic else (11, 16)
    return rng.randint(low, high) / 2


def _client_entries(rng: random.Random, client: User, now: datetime) -> list[Entry]:
    entries: list[Entry] = []
    # Separate stream, so adding sleep did not change any other seeded value.
    sleep_rng = random.Random(f"sleep-{client.email}")  # noqa: S311  (demo data)
    for days_ago in range(21, 0, -1):
        day = now - timedelta(days=days_ago)
        kinds = [EntryKind.MEDICATION]
        if rng.random() < 0.7:
            kinds.append(EntryKind.QUICK)
        if rng.random() < 0.2:
            kinds.append(EntryKind.PANIC)
        if rng.random() < 0.15:
            kinds.append(EntryKind.AVOIDANCE)
        for kind in kinds:
            note, details = _entry_payload(rng, kind)
            if kind == EntryKind.QUICK:
                details["sleep_hours"] = _sleep_hours(sleep_rng, EntryKind.PANIC in kinds)
            entries.append(
                Entry(
                    organization_id=client.organization_id,
                    client_id=client.id,
                    kind=kind,
                    occurred_at=day.replace(hour=rng.randint(8, 22), minute=rng.randint(0, 59)),
                    note=note,
                    details=details,
                )
            )
    return entries


def _demo_summary(
    client: User,
    entries: list[Entry],
    previous: Appointment,
    upcoming: Appointment,
    shared_at: datetime,
) -> tuple[Summary, list[tuple[SummaryStatement, list[Entry]]]]:
    """A fixed, pre-written shared summary (no LLM call). Each statement cites the real seeded
    entries it describes; counts are computed from those entries so the text stays accurate."""
    start = previous.scheduled_at
    window = [e for e in entries if start <= e.occurred_at <= shared_at]
    by_kind = {k: [e for e in window if e.kind == k] for k in EntryKind}
    drafts: list[tuple[str, str, list[Entry]]] = []
    if panics := by_kind[EntryKind.PANIC]:
        drafts.append(
            (
                "Atak kayıtları",
                f"Bu dönemde {len(panics)} atak kaydı var; ortalama şiddet "
                f"{sum(e.details['intensity'] for e in panics) / len(panics):.1f}/10 olarak "
                "işaretlenmiş.",
                panics,
            )
        )
    if quicks := by_kind[EntryKind.QUICK]:
        drafts.append(
            ("Günlük notlar", "Günlük notlarda uyku, gerginlik ve yürüyüş geçiyor.", quicks)
        )
    if avoids := by_kind[EntryKind.AVOIDANCE]:
        drafts.append(
            (
                "Kaçınma",
                f"{len(avoids)} durumda kaçınma kaydı tutulmuş.",
                avoids,
            )
        )
    meds = by_kind[EntryKind.MEDICATION]
    drafts.append(
        (
            "İlaç kaydı",
            f"{len(meds)} günlük ilaç kaydında "
            f"{sum(1 for e in meds if e.details['taken'])} gün ilacın alındığı işaretlenmiş.",
            meds,
        )
    )
    statements = [
        (SummaryStatement(position=i, section=sec, text=text), cited)
        for i, (sec, text, cited) in enumerate(drafts)
    ]
    summary = Summary(
        organization_id=client.organization_id,
        client_id=client.id,
        title="Seans öncesi özet",
        body=render_body([st for st, _ in statements]),
        status=SummaryStatus.SHARED,
        period_start=start.date(),
        period_end=shared_at.date(),
        approved_at=shared_at,
        shared_at=shared_at,
        appointment_id=upcoming.id,
        topics=["Metroda yaşadığım atak", "Uyku düzenim"],
    )
    return summary, statements


async def seed(session: AsyncSession, *, password: str, now: datetime | None = None) -> list[str]:
    """Creates missing demo organizations (all users share `password`). Returns created slugs."""
    password_hash = await hash_password(password)
    now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    rng = random.Random(42)  # noqa: S311 — deterministic demo data, not security-relevant
    created: list[str] = []

    for spec in ORGS:
        exists = await session.scalar(select(Organization.id).where(Organization.slug == spec.slug))
        if exists:
            continue
        org = Organization(slug=spec.slug, name=spec.name)
        session.add(org)
        await session.flush()

        users = [
            User(
                organization_id=org.id,
                email=u.email,
                display_name=u.display_name,
                role=u.role,
                password_hash=password_hash,
            )
            for u in spec.users
        ]
        session.add_all(users)
        await session.flush()

        clinicians = [u for u in users if u.role == UserRole.CLINICIAN]
        for client in (u for u in users if u.role == UserRole.CLIENT):
            assigned = rng.choice(clinicians)
            if client.email == AYSE_EMAIL:  # the demo plan-sharing story needs Dr. Elif
                assigned = next(c for c in clinicians if c.email == ELIF_EMAIL)
            session.add(
                CareAssignment(
                    organization_id=org.id, clinician_id=assigned.id, client_id=client.id
                )
            )
            entries = _client_entries(rng, client, now)
            session.add_all(entries)
            next_session = (now + timedelta(days=rng.randint(1, 6))).replace(hour=14, minute=0)
            appointments = [
                Appointment(
                    organization_id=org.id,
                    client_id=client.id,
                    clinician_id=assigned.id,
                    created_by_id=assigned.id,
                    kind=AppointmentKind.THERAPY,
                    scheduled_at=when,
                )
                for when in (next_session - timedelta(days=7), next_session)
            ]
            session.add_all(appointments)
            plan = _demo_plan(client)
            if client.email == AYSE_EMAIL:
                # Taken now (not `now`): sharing only counts if it is after the assignment,
                # whose timestamp is the start of this transaction.
                plan.shared_at = datetime.now(UTC)
            session.add(plan)
            if client.email == AYSE_EMAIL:
                await session.flush()  # entry/appointment ids are needed for the citations
                summary, statements = _demo_summary(
                    client, entries, *appointments, shared_at=datetime.now(UTC)
                )
                session.add(summary)
                await session.flush()
                for statement, cited in statements:
                    statement.summary_id = summary.id
                    session.add(statement)
                    await session.flush()
                    session.add_all(
                        SummaryCitation(statement_id=statement.id, entry_id=e.id) for e in cited
                    )
        created.append(spec.slug)

    await session.commit()
    return created


async def reset_demo(session: AsyncSession) -> list[str]:
    """Deletes the demo organizations (only the slugs in `ORGS`) and every row they own, so
    `seed` can recreate them. Audit logs are kept on purpose (they must outlive the rows they
    refer to); a `demo_reset` record is added instead. Returns the deleted slugs."""
    rows = (
        await session.execute(
            select(Organization.id, Organization.slug).where(
                Organization.slug.in_([o.slug for o in ORGS])
            )
        )
    ).all()
    if not rows:
        return []
    org_ids = [r.id for r in rows]
    # Dependents first. Tables without `organization_id` (summary statements/citations,
    # refresh tokens) are removed by ON DELETE CASCADE from their parents.
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in ("audit_logs", "organizations") or "organization_id" not in table.c:
            continue
        await session.execute(delete(table).where(table.c.organization_id.in_(org_ids)))
    await session.execute(delete(Organization).where(Organization.id.in_(org_ids)))
    session.add_all(
        AuditLog(
            organization_id=r.id,
            action="demo_reset",
            target_type="organization",
            target_id=r.id,
            detail={"slug": r.slug},
        )
        for r in rows
    )
    await session.commit()
    return [r.slug for r in rows]


def ensure_seed_allowed(settings: Settings) -> None:
    """Production seeding needs SEED_DEMO=1 and an explicit SEED_PASSWORD (never printed)."""
    if not settings.is_production:
        return
    if not settings.seed_demo:
        raise SystemExit("Refusing to seed demo data in production (set SEED_DEMO=1 to allow).")
    if settings.seed_password is None or len(settings.seed_password.get_secret_value()) < 12:
        raise SystemExit("SEED_DEMO in production requires SEED_PASSWORD (at least 12 characters).")


async def main(*, reset: bool = False) -> None:
    settings = get_settings()
    ensure_seed_allowed(settings)
    password = (
        settings.seed_password.get_secret_value()
        if settings.seed_password
        else secrets.token_urlsafe(12)
    )
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            if reset:
                deleted = await reset_demo(session)
                print(f"Deleted demo organizations: {deleted or 'none'}")  # noqa: T201
            created = await seed(session, password=password)
    finally:
        await engine.dispose()
    print(f"Seeded organizations: {created or 'none (already present)'}")  # noqa: T201
    if created and not settings.seed_password:
        print(f"Password for all seeded users (shown once): {password}")  # noqa: T201


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed synthetic demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo organizations (and everything in them) before seeding",
    )
    asyncio.run(main(reset=parser.parse_args().reset))
