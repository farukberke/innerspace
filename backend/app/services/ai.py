"""AI flows. The backend decides what the model may see (deps) and what may be stored
(validated output); crisis detection runs before any model call. No content is logged."""

import json
from datetime import UTC, date, datetime, time, timedelta

from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.after_session_agent import AfterSessionOutput, after_session_agent, build_prompt
from app.ai.crisis import contains_crisis_language
from app.ai.llm import run_agent
from app.ai.summary_agent import SummaryDeps, SummaryDraft, summary_agent
from app.core.config import Settings
from app.models import (
    AfterSessionNote,
    Entry,
    Summary,
    SummaryCitation,
    SummaryJob,
    SummaryJobStatus,
    SummaryStatement,
    SummaryStatus,
    User,
)
from app.services import audit, summaries
from app.services.entries import entries_in_period
from app.services.errors import CrisisDetectedError, ValidationFailedError


async def _record_crisis(session: AsyncSession, client: User, source: str) -> None:
    await audit.record(
        session,
        "ai.crisis_detected",
        organization_id=client.organization_id,
        actor_id=client.id,
        detail={"source": source},
    )
    await session.commit()


def _period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, UTC),
        datetime.combine(end + timedelta(days=1), time.min, UTC),
    )


def _to_statements(draft: SummaryDraft) -> list[SummaryStatement]:
    statements: list[SummaryStatement] = []
    for section in draft.sections:
        for st in section.statements:
            statement = SummaryStatement(
                position=len(statements), section=section.heading, text=st.text
            )
            statement.citations = [
                SummaryCitation(entry_id=entry_id)
                for entry_id in dict.fromkeys(st.source_entry_ids)
            ]
            statements.append(statement)
    return statements


async def generate_summary(
    session: AsyncSession,
    settings: Settings,
    model: Model,
    client: User,
    start: date,
    end: date,
    job: SummaryJob | None = None,
) -> Summary:
    """If a background `job` is given it is marked succeeded in the same transaction that
    stores the summary, so a summary never exists without its job being settled."""
    lo, hi = _period_bounds(start, end)
    entries = (
        await session.scalars(
            entries_in_period(client.id, client.organization_id, lo, hi).order_by(Entry.occurred_at)
        )
    ).all()
    if not entries:
        raise ValidationFailedError("There are no entries in the selected period")
    # Rule-based safety check on the raw records, before any LLM call.
    if any(
        contains_crisis_language(e.note, json.dumps(e.details, ensure_ascii=False)) for e in entries
    ):
        await _record_crisis(session, client, "entries")
        raise CrisisDetectedError

    deps = SummaryDeps(
        session=session,
        client_id=client.id,
        organization_id=client.organization_id,
        start=lo,
        end=hi,
    )
    draft = await run_agent(
        session,
        settings,
        model,
        client,
        "session_summary",
        summary_agent,
        "Prepare the pre-session summary of my records for the selected period.",
        deps,
    )
    statements = _to_statements(draft)
    summary = Summary(
        organization_id=client.organization_id,
        client_id=client.id,
        title=draft.title,
        body=summaries.render_body(statements),
        status=SummaryStatus.DRAFT,
        period_start=start,
        period_end=end,
        statements=statements,
    )
    session.add(summary)
    await session.flush()
    await audit.record(
        session,
        "summary.generate",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="summary",
        target_id=summary.id,
        detail={"entries": len(entries), "statements": len(statements)},
    )
    if job is not None:
        job.status = SummaryJobStatus.SUCCEEDED
        job.summary_id = summary.id
        job.error_code = None
    await session.commit()
    return summary


async def create_after_session_note(
    session: AsyncSession, settings: Settings, model: Model, client: User, text: str
) -> AfterSessionNote:
    if contains_crisis_language(text):
        await _record_crisis(session, client, "after_session")
        raise CrisisDetectedError
    output: AfterSessionOutput = await run_agent(
        session,
        settings,
        model,
        client,
        "after_session",
        after_session_agent,
        build_prompt(text),
        None,
    )
    note = AfterSessionNote(
        organization_id=client.organization_id,
        client_id=client.id,
        source_text=text,
        discussed=output.discussed,
        to_try=output.to_try,
        questions=output.questions,
    )
    session.add(note)
    await session.flush()
    await audit.record(
        session,
        "after_session.generate",
        organization_id=client.organization_id,
        actor_id=client.id,
        target_type="after_session_note",
        target_id=note.id,
    )
    await session.commit()
    return note


async def list_after_session_notes(session: AsyncSession, client: User) -> list[AfterSessionNote]:
    query = (
        select(AfterSessionNote)
        .where(
            AfterSessionNote.client_id == client.id,
            AfterSessionNote.organization_id == client.organization_id,
        )
        .order_by(AfterSessionNote.created_at.desc(), AfterSessionNote.id)
    )
    return list((await session.scalars(query)).all())
