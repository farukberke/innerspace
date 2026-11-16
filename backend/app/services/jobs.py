"""Background summary jobs: idempotent creation, atomic claiming, outcome handling.

A job holds no content, only status and a short error code. The worker re-reads everything
from the database scoped to the job's client and organization."""

import enum
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from pydantic_ai.models import Model
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import AiGenerationError
from app.core.config import Settings
from app.models import SummaryJob, SummaryJobStatus, User, UserRole
from app.services import ai
from app.services.errors import (
    ConflictError,
    CrisisDetectedError,
    NotFoundError,
    ValidationFailedError,
)

logger = logging.getLogger(__name__)

_RUNNING = SummaryJobStatus.RUNNING


class JobOutcome(enum.Enum):
    DONE = "done"  # settled (succeeded, failed or crisis)
    SKIPPED = "skipped"  # not claimable: already running or finished (e.g. duplicate delivery)
    RETRY = "retry"  # transient failure; the job is queued again


async def _find(
    session: AsyncSession, client: User, key: str | None, start: date, end: date
) -> SummaryJob | None:
    query = select(SummaryJob).where(SummaryJob.client_id == client.id)
    if key is not None:
        query = query.where(SummaryJob.idempotency_key == key)
    else:
        query = query.where(
            SummaryJob.idempotency_key.is_(None),
            SummaryJob.period_start == start,
            SummaryJob.period_end == end,
            SummaryJob.status.in_([SummaryJobStatus.QUEUED, SummaryJobStatus.RUNNING]),
        )
    return await session.scalar(query)


async def create_or_get(
    session: AsyncSession,
    client: User,
    start: date,
    end: date,
    key: str | None,
    appointment_id: uuid.UUID | None = None,
) -> tuple[SummaryJob, bool]:
    """Returns (job, created). The database unique constraints decide races: the loser of a
    concurrent insert gets the winner's job."""
    existing = await _find(session, client, key, start, end)
    if existing is None:
        job = SummaryJob(
            organization_id=client.organization_id,
            client_id=client.id,
            period_start=start,
            period_end=end,
            status=SummaryJobStatus.QUEUED,
            attempts=0,
            idempotency_key=key,
            appointment_id=appointment_id,
        )
        try:
            async with session.begin_nested():
                session.add(job)
        except IntegrityError:
            existing = await _find(session, client, key, start, end)
            if existing is None:
                raise
        else:
            await session.commit()
            return job, True
    if (existing.period_start, existing.period_end, existing.appointment_id) != (
        start,
        end,
        appointment_id,
    ):
        raise ConflictError("Idempotency-Key was already used with a different request")
    return existing, False


async def get_own(session: AsyncSession, client: User, job_id: uuid.UUID) -> SummaryJob:
    job = await session.scalar(
        select(SummaryJob).where(
            SummaryJob.id == job_id,
            SummaryJob.client_id == client.id,
            SummaryJob.organization_id == client.organization_id,
        )
    )
    if job is None:
        raise NotFoundError
    return job


async def _transition(
    session: AsyncSession,
    job_id: uuid.UUID,
    expected: SummaryJobStatus,
    status: SummaryJobStatus,
    error_code: str | None = None,
) -> None:
    """Conditional UPDATE: only moves the job if it is still in the expected status."""
    await session.execute(
        update(SummaryJob)
        .where(SummaryJob.id == job_id, SummaryJob.status == expected)
        .values(status=status, error_code=error_code)
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def fail_queued(session: AsyncSession, job_id: uuid.UUID, error_code: str) -> None:
    await _transition(session, job_id, SummaryJobStatus.QUEUED, SummaryJobStatus.FAILED, error_code)


async def _claim(session: AsyncSession, job_id: uuid.UUID) -> SummaryJob | None:
    """queued -> running exactly once (atomic conditional UPDATE)."""
    claimed = await session.scalar(
        update(SummaryJob)
        .where(SummaryJob.id == job_id, SummaryJob.status == SummaryJobStatus.QUEUED)
        .values(status=_RUNNING, attempts=SummaryJob.attempts + 1)
        .returning(SummaryJob.id)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    if claimed is None:
        return None
    return await session.get(SummaryJob, job_id, populate_existing=True)


async def run(
    session: AsyncSession,
    settings: Settings,
    model: Model,
    job_id: uuid.UUID,
    *,
    final_attempt: bool,
) -> JobOutcome:
    """Processes one job. Transient failures re-queue it (unless `final_attempt`); permanent
    ones fail it with an error code. Never logs or stores content."""
    job = await _claim(session, job_id)
    if job is None:
        return JobOutcome.SKIPPED

    async def settle(status: SummaryJobStatus, code: str | None = None) -> None:
        await _transition(session, job_id, _RUNNING, status, code)

    try:
        client = await session.scalar(
            select(User).where(
                User.id == job.client_id,
                User.organization_id == job.organization_id,
                User.role == UserRole.CLIENT,
            )
        )
        if client is None or not client.is_active:
            await settle(SummaryJobStatus.FAILED, "client_inactive")
            return JobOutcome.DONE
        await ai.generate_summary(
            session, settings, model, client, job.period_start, job.period_end, job
        )
    except CrisisDetectedError:
        await settle(SummaryJobStatus.CRISIS)
    except ValidationFailedError:
        await settle(SummaryJobStatus.FAILED, "validation_failed")
    except AiGenerationError as exc:
        await session.rollback()
        if exc.transient and not final_attempt:
            await settle(SummaryJobStatus.QUEUED)
            return JobOutcome.RETRY
        await settle(
            SummaryJobStatus.FAILED, "ai_unavailable" if exc.transient else "generation_failed"
        )
    except (OperationalError, InterfaceError):
        await session.rollback()
        if final_attempt:
            await settle(SummaryJobStatus.FAILED, "database_unavailable")
            return JobOutcome.DONE
        await settle(SummaryJobStatus.QUEUED)
        return JobOutcome.RETRY
    except Exception as exc:
        await session.rollback()
        logger.error("summary job crashed", extra={"error_type": type(exc).__name__})
        await settle(SummaryJobStatus.FAILED, "internal_error")
    return JobOutcome.DONE


async def reap_stale(
    session: AsyncSession, stale_after_seconds: int, max_attempts: int
) -> list[uuid.UUID]:
    """Recovers jobs stuck in `running` (the worker died): back to `queued` while attempts
    remain, otherwise `failed`. Returns the ids to enqueue again. Idempotent and safe to run
    concurrently: both steps are conditional UPDATEs on the stale `running` state."""
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
    stale = (SummaryJob.status == _RUNNING, SummaryJob.updated_at < cutoff)
    requeued = (
        await session.scalars(
            update(SummaryJob)
            .where(*stale, SummaryJob.attempts < max_attempts)
            .values(status=SummaryJobStatus.QUEUED)
            .returning(SummaryJob.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    failed = (
        await session.scalars(
            update(SummaryJob)
            .where(*stale, SummaryJob.attempts >= max_attempts)
            .values(status=SummaryJobStatus.FAILED, error_code="stale_timeout")
            .returning(SummaryJob.id)
            .execution_options(synchronize_session=False)
        )
    ).all()
    await session.commit()
    if requeued or failed:
        logger.warning(
            "stale jobs reaped", extra={"requeued": len(requeued), "failed": len(failed)}
        )
    return list(requeued)
