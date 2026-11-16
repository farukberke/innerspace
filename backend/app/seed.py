"""Synthetic demo data. Everything here is fictional — no real people or health data.

Usage (from `backend/`):  uv run python -m app.seed
Production (demo deployment): SEED_DEMO=1 SEED_PASSWORD=<12+ chars> python -m app.seed
Idempotent: organizations that already exist (by slug) are skipped.
"""

import asyncio
import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_sessionmaker
from app.core.security import hash_password
from app.models import (
    Appointment,
    AppointmentKind,
    CareAssignment,
    Entry,
    EntryKind,
    Organization,
    User,
    UserRole,
)


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
        name="Demo Clinic (synthetic)",
        users=(
            SeedUser("admin@demo-clinic.test", "Deniz Admin", UserRole.ORG_ADMIN),
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
        name="Other Clinic (synthetic)",
        users=(
            SeedUser("admin@other-clinic.test", "Ozan Admin", UserRole.ORG_ADMIN),
            SeedUser("dr.selin@other-clinic.test", "Dr. Selin Er", UserRole.CLINICIAN),
            SeedUser("client.emre@other-clinic.test", "Emre K.", UserRole.CLIENT),
        ),
    ),
)

_QUICK_NOTES = (
    "Slept badly, felt tense most of the morning.",
    "Good walk after work, mood lifted a bit.",
    "Argument with a colleague; kept replaying it in my head.",
    "Quiet day. Tried the breathing exercise twice.",
    "Felt more like myself today.",
)
_PANIC_SYMPTOMS = ("racing heart", "shortness of breath", "dizziness", "sweating", "trembling")
_PANIC_TRIGGERS = ("crowded metro", "work meeting", "no clear trigger", "supermarket queue")
_AVOIDANCE_SITUATIONS = ("taking the metro", "a friend's birthday dinner", "phone call to the bank")


def _entry_payload(rng: random.Random, kind: EntryKind) -> tuple[str | None, dict[str, Any]]:
    match kind:
        case EntryKind.QUICK:
            return rng.choice(_QUICK_NOTES), {"mood": rng.randint(1, 5)}
        case EntryKind.PANIC:
            return "Episode passed after a while.", {
                "intensity": rng.randint(4, 9),
                "duration_minutes": rng.choice((5, 10, 15, 25)),
                "symptoms": rng.sample(_PANIC_SYMPTOMS, k=rng.randint(1, 3)),
                "trigger": rng.choice(_PANIC_TRIGGERS),
            }
        case EntryKind.MEDICATION:
            taken = rng.random() > 0.15
            return None, {
                "medication_name": "Medication A (fictional)",
                "taken": taken,
                "side_effects": ["mild nausea"] if taken and rng.random() < 0.2 else [],
            }
        case EntryKind.AVOIDANCE:
            return None, {
                "situation": rng.choice(_AVOIDANCE_SITUATIONS),
                "avoided": rng.random() < 0.6,
                "anxiety": rng.randint(3, 9),
            }


def _client_entries(rng: random.Random, client: User, now: datetime) -> list[Entry]:
    entries: list[Entry] = []
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
            session.add(
                CareAssignment(
                    organization_id=org.id, clinician_id=assigned.id, client_id=client.id
                )
            )
            session.add_all(_client_entries(rng, client, now))
            next_session = (now + timedelta(days=rng.randint(1, 6))).replace(hour=14, minute=0)
            session.add_all(
                [
                    Appointment(
                        organization_id=org.id,
                        client_id=client.id,
                        clinician_id=assigned.id,
                        kind=AppointmentKind.THERAPY,
                        scheduled_at=next_session - timedelta(days=7),
                    ),
                    Appointment(
                        organization_id=org.id,
                        client_id=client.id,
                        clinician_id=assigned.id,
                        kind=AppointmentKind.THERAPY,
                        scheduled_at=next_session,
                    ),
                ]
            )
        created.append(spec.slug)

    await session.commit()
    return created


def ensure_seed_allowed(settings: Settings) -> None:
    """Production seeding needs SEED_DEMO=1 and an explicit SEED_PASSWORD (never printed)."""
    if not settings.is_production:
        return
    if not settings.seed_demo:
        raise SystemExit("Refusing to seed demo data in production (set SEED_DEMO=1 to allow).")
    if settings.seed_password is None or len(settings.seed_password.get_secret_value()) < 12:
        raise SystemExit("SEED_DEMO in production requires SEED_PASSWORD (at least 12 characters).")


async def main() -> None:
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
            created = await seed(session, password=password)
    finally:
        await engine.dispose()
    print(f"Seeded organizations: {created or 'none (already present)'}")  # noqa: T201
    if created and not settings.seed_password:
        print(f"Password for all seeded users (shown once): {password}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
