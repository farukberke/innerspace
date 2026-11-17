"""Summaries: private to the client until shared; clinicians see only shared ones of clients
assigned to them. Every query is scoped by organization and ownership/assignment."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.crisis import contains_crisis_language
from app.ai.guardrails import find_violations
from app.models import (
    CareAssignment,
    Summary,
    SummaryReceipt,
    SummaryStatement,
    SummaryStatus,
    User,
)
from app.services import audit
from app.services.errors import (
    ConflictError,
    CrisisDetectedError,
    NotFoundError,
    ValidationFailedError,
)

GUARDRAIL_MESSAGE = "The text must not contain a diagnosis or medication, dose or treatment advice"


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
            Summary.status == SummaryStatus.SHARED,
            # A clinician assigned after the sharing sees nothing until the client
            # shares again (otherwise assigning a new clinician would expose old data).
            Summary.shared_at >= CareAssignment.created_at,
        )
    )


async def list_own(session: AsyncSession, client: User) -> list[Summary]:
    query = _owned_by(client).order_by(Summary.created_at.desc(), Summary.id)
    return list((await session.scalars(query)).all())


async def get_own(session: AsyncSession, client: User, summary_id: uuid.UUID) -> Summary:
    summary = await session.scalar(_owned_by(client).where(Summary.id == summary_id))
    if summary is None:
        raise NotFoundError
    return summary


def render_body(statements: list[SummaryStatement]) -> str:
    """Plain-text body derived from the statements (grouped by consecutive section)."""
    lines: list[str] = []
    current: str | None = None
    for st in sorted(statements, key=lambda x: x.position):
        if st.section != current:
            current = st.section
            lines += ["", f"## {current}"] if lines else [f"## {current}"]
        lines.append(f"- {st.text}")
    return "\n".join(lines)


async def update_draft(
    session: AsyncSession,
    client: User,
    summary_id: uuid.UUID,
    title: str | None,
    edits: dict[uuid.UUID, str],
) -> Summary:
    """Client edits an AI draft. The edited text passes the same guardrails as AI output, and
    the summary returns to `draft` so it must be approved again."""
    summary = await get_own(session, client, summary_id)
    if summary.status == SummaryStatus.SHARED:
        raise ConflictError("Revoke sharing before editing this summary")
    by_id = {st.id: st for st in summary.statements}
    if not edits.keys() <= by_id.keys():
        raise ValidationFailedError("Unknown statement id")
    if find_violations(*edits.values(), *([title] if title else [])):
        raise ValidationFailedError(GUARDRAIL_MESSAGE)
    if title:
        summary.title = title
    for statement_id, text in edits.items():
        by_id[statement_id].text = text
    summary.body = render_body(summary.statements) if summary.statements else summary.body
    summary.status = SummaryStatus.DRAFT
    summary.approved_at = None
    await audit.record(
        session,
        "summary.edit",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="summary",
        target_id=summary.id,
    )
    await session.commit()
    return summary


async def set_topics(
    session: AsyncSession, client: User, summary_id: uuid.UUID, topics: list[str]
) -> Summary:
    """The client's own "topics to talk about". Same edit rule as the statements: not while
    shared; saving returns the summary to `draft` (re-approval). The text is untrusted input:
    crisis language yields the fixed crisis response (nothing saved), and the guardrails apply."""
    summary = await get_own(session, client, summary_id)
    if summary.status == SummaryStatus.SHARED:
        raise ConflictError("Revoke sharing before editing this summary")
    if contains_crisis_language(*topics):
        await audit.record(
            session,
            "ai.crisis_detected",
            organization_id=client.organization_id,
            actor_id=client.id,
            detail={"source": "topics"},
        )
        await session.commit()
        raise CrisisDetectedError
    if find_violations(*topics):
        raise ValidationFailedError(GUARDRAIL_MESSAGE)
    summary.topics = list(topics)
    summary.status = SummaryStatus.DRAFT
    summary.approved_at = None
    await audit.record(
        session,
        "summary.topics_update",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="summary",
        target_id=summary.id,
    )
    await session.commit()
    return summary


async def approve(session: AsyncSession, client: User, summary_id: uuid.UUID) -> Summary:
    """The client's review step: nothing can be shared before it. Idempotent."""
    summary = await get_own(session, client, summary_id)
    if summary.status != SummaryStatus.DRAFT:
        return summary
    if find_violations(summary.title, summary.body, *summary.topics):
        raise ValidationFailedError(GUARDRAIL_MESSAGE)
    summary.status = SummaryStatus.APPROVED
    summary.approved_at = datetime.now(UTC)
    await audit.record(
        session,
        "summary.approve",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="summary",
        target_id=summary.id,
    )
    await session.commit()
    return summary


async def set_shared(
    session: AsyncSession, client: User, summary_id: uuid.UUID, shared: bool
) -> Summary:
    """Sharing is the client's explicit second decision, possible only after approval;
    revoking removes clinician access. Both are idempotent."""
    summary = await get_own(session, client, summary_id)
    if shared:
        if summary.status == SummaryStatus.DRAFT:
            raise ConflictError("Approve the summary before sharing it")
        # Sharing again (even when already shared) renews `shared_at`: that is how the
        # client lets clinicians assigned since the last share see the summary.
        summary.status = SummaryStatus.SHARED
        summary.shared_at = datetime.now(UTC)
    else:
        if summary.status != SummaryStatus.SHARED:
            return summary
        summary.status = SummaryStatus.REVOKED
        summary.shared_at = None
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


def _is_new() -> ColumnElement[bool]:
    """True while the summary was never opened by the receipt's clinician, or re-shared since."""
    return or_(SummaryReceipt.read_at.is_(None), SummaryReceipt.read_at < Summary.shared_at)


def _visible_with_flag(clinician: User) -> Select[Any]:
    """`_shared_with(clinician)` plus an `is_new` column for that clinician."""
    return (
        _shared_with(clinician)
        .add_columns(_is_new().label("is_new"))
        .outerjoin(
            SummaryReceipt,
            (SummaryReceipt.summary_id == Summary.id)
            & (SummaryReceipt.clinician_id == clinician.id),
        )
    )


async def list_shared_with(session: AsyncSession, clinician: User) -> list[tuple[Summary, bool]]:
    """Shared summaries visible to `clinician`, newest share first, each with its "new" flag."""
    query = _visible_with_flag(clinician).order_by(Summary.shared_at.desc(), Summary.id)
    return [(summary, bool(is_new)) for summary, is_new in await session.execute(query)]


async def sharing_overview(
    session: AsyncSession, clinician: User
) -> dict[uuid.UUID, tuple[datetime, int]]:
    """Per assigned client: latest share and number of unopened shares, counting only the
    summaries this clinician may see (same scope as `list_shared_with`). Metadata only."""
    visible = _visible_with_flag(clinician).subquery()
    query = select(
        visible.c.client_id,
        func.max(visible.c.shared_at),
        func.count().filter(visible.c.is_new),
    ).group_by(visible.c.client_id)
    return {client_id: (last, int(new)) for client_id, last, new in await session.execute(query)}


async def get_shared_with(session: AsyncSession, clinician: User, summary_id: uuid.UUID) -> Summary:
    summary = await session.scalar(_shared_with(clinician).where(Summary.id == summary_id))
    if summary is None:
        raise NotFoundError
    upsert = insert(SummaryReceipt).values(
        summary_id=summary.id,
        clinician_id=clinician.id,
        organization_id=clinician.organization_id,
        read_at=datetime.now(UTC),
    )
    await session.execute(
        upsert.on_conflict_do_update(
            index_elements=[SummaryReceipt.summary_id, SummaryReceipt.clinician_id],
            set_={"read_at": upsert.excluded.read_at},
        )
    )
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
