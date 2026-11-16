"""The client's support plan ("Planım"). Private to the client; the assigned clinician sees it
read-only only while the client has shared it (same rule as summaries: sharing counts only if
`shared_at >= assignment.created_at`). `org_admin` has no access. No AI is involved."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CareAssignment, SupportPlan, User
from app.schemas.planning import PlanContact, PlanContent
from app.services import audit, people
from app.services.errors import NotFoundError


def _owned_by(client: User) -> Select[tuple[SupportPlan]]:
    return select(SupportPlan).where(
        SupportPlan.client_id == client.id, SupportPlan.organization_id == client.organization_id
    )


async def get_own(session: AsyncSession, client: User) -> SupportPlan | None:
    return await session.scalar(_owned_by(client))


def _apply(plan: SupportPlan, content: PlanContent) -> None:
    plan.moment_steps = list(content.moment_steps)
    plan.self_note = content.self_note
    plan.contacts = [c.model_dump() for c in content.contacts]
    plan.warning_signs = list(content.warning_signs)
    plan.coping_strategies = list(content.coping_strategies)
    plan.talk_to_clinician = list(content.talk_to_clinician)


async def save_own(session: AsyncSession, client: User, content: PlanContent) -> SupportPlan:
    """Creates or replaces the client's plan. Sharing state is unchanged by an edit."""
    plan = await get_own(session, client)
    if plan is None:
        plan = SupportPlan(organization_id=client.organization_id, client_id=client.id)
        _apply(plan, content)
        session.add(plan)
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:  # concurrent first save: the other request won
            session.expunge(plan)
            existing = await get_own(session, client)
            if existing is None:
                raise
            plan = existing
            _apply(plan, content)
    else:
        _apply(plan, content)
    await audit.record(
        session,
        "plan.update",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="plan",
        target_id=plan.id,
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def set_shared(session: AsyncSession, client: User, shared: bool) -> SupportPlan:
    """Sharing is the client's explicit decision; sharing again renews `shared_at` (so a
    clinician assigned since can see it); revoking ends access. Both are idempotent."""
    plan = await get_own(session, client)
    if plan is None:
        raise NotFoundError
    if shared:
        plan.shared_at = datetime.now(UTC)
    elif plan.shared_at is None:
        return plan
    else:
        plan.shared_at = None
    await audit.record(
        session,
        "plan.share" if shared else "plan.unshare",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="plan",
        target_id=plan.id,
    )
    await session.commit()
    await session.refresh(plan)
    return plan


async def get_shared_with(
    session: AsyncSession, clinician: User, client_id: uuid.UUID
) -> SupportPlan:
    """The shared plan of an assigned client; anything else is NotFound. Audited."""
    await people.get_assigned_client(session, clinician, client_id)
    plan = await session.scalar(
        select(SupportPlan)
        .join(
            CareAssignment,
            (CareAssignment.client_id == SupportPlan.client_id)
            & (CareAssignment.organization_id == SupportPlan.organization_id),
        )
        .where(
            SupportPlan.client_id == client_id,
            SupportPlan.organization_id == clinician.organization_id,
            CareAssignment.clinician_id == clinician.id,
            SupportPlan.shared_at.is_not(None),
            SupportPlan.shared_at >= CareAssignment.created_at,
        )
    )
    if plan is None:
        raise NotFoundError
    await audit.record(
        session,
        "plan.view",
        organization_id=clinician.organization_id,
        actor_id=clinician.id,
        target_type="plan",
        target_id=plan.id,
    )
    await session.commit()
    return plan


async def crisis_contacts(session: AsyncSession, client: User) -> list[PlanContact]:
    """The client's own plan contacts, shown next to the fixed crisis message."""
    plan = await get_own(session, client)
    if plan is None:
        return []
    return [PlanContact.model_validate(c) for c in plan.contacts]
