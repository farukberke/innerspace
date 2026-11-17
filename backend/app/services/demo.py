"""One-click demo sign-in for the public demo deployment.

Only the seeded `demo-clinic` accounts below can be signed into this way, only while
`DEMO_LOGIN_ENABLED` is on, and never without an audit record. The accounts carry synthetic
data only. While demo login is on, the org admin cannot deactivate these accounts or remove
the assignment between the demo client and clinician, so one visitor cannot break the demo
for the next one.
"""

import uuid
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Organization, User, UserRole
from app.services import audit
from app.services.auth import issue_tokens
from app.services.errors import NotFoundError

DEMO_ORG_SLUG = "demo-clinic"


class DemoRole(StrEnum):
    CLIENT = "client"
    CLINICIAN = "clinician"
    ORG_ADMIN = "org_admin"


DEMO_ACCOUNTS: dict[DemoRole, str] = {
    DemoRole.CLIENT: "client.ayse@demo-clinic.test",
    DemoRole.CLINICIAN: "dr.elif@demo-clinic.test",
    DemoRole.ORG_ADMIN: "admin@demo-clinic.test",
}


async def _demo_user(session: AsyncSession, role: DemoRole) -> User | None:
    return await session.scalar(
        select(User)
        .join(Organization, Organization.id == User.organization_id)
        .where(
            Organization.slug == DEMO_ORG_SLUG,
            User.email == DEMO_ACCOUNTS[role],
            User.role == UserRole(role.value),
            User.is_active.is_(True),
        )
    )


async def sign_in(session: AsyncSession, settings: Settings, role: DemoRole) -> tuple[str, str]:
    """Returns (access, refresh) for the demo account of `role`. NotFoundError when demo login
    is off or the seeded account is missing/inactive (the caller answers 404 either way)."""
    if not settings.demo_login_enabled:
        raise NotFoundError
    user = await _demo_user(session, role)
    if user is None:
        raise NotFoundError
    await audit.record(
        session,
        "auth.demo_login",
        organization_id=user.organization_id,
        actor_id=user.id,
        detail={"role": role.value},
    )
    tokens = await issue_tokens(session, settings, user)
    await session.commit()
    return tokens


async def protected_ids(session: AsyncSession, settings: Settings) -> frozenset[uuid.UUID]:
    """Ids of the demo-login accounts, which stay active and assigned while demo login is on."""
    if not settings.demo_login_enabled:
        return frozenset()
    rows = await session.scalars(
        select(User.id)
        .join(Organization, Organization.id == User.organization_id)
        .where(Organization.slug == DEMO_ORG_SLUG, User.email.in_(DEMO_ACCOUNTS.values()))
    )
    return frozenset(rows.all())
