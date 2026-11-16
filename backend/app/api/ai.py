import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response, status

from app.ai.crisis import CRISIS_MESSAGE, CRISIS_RESOURCES
from app.ai.llm import AiGenerationError
from app.api.deps import (
    CurrentClient,
    JobEnqueuerDep,
    LlmModelDep,
    SessionDep,
    SettingsDep,
    limit_per_user,
)
from app.models import SummaryJobStatus
from app.schemas.care import (
    AfterSessionCreate,
    AfterSessionRead,
    CrisisResponse,
    SummaryGenerate,
    SummaryJobRead,
)
from app.services import ai as service
from app.services import jobs, usage
from app.services.errors import ConflictError, CrisisDetectedError, NotFoundError

router = APIRouter(tags=["ai"])
logger = logging.getLogger(__name__)

_CRISIS = CrisisResponse(message=CRISIS_MESSAGE, resources=CRISIS_RESOURCES)


def _generation_failed(exc: AiGenerationError) -> HTTPException:
    logger.warning("ai generation failed", extra={"error_type": str(exc)})
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        "Could not produce a safe result right now. Please try again later.",
    )


@router.post(
    "/summaries/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_per_user("generate"))],
)
async def generate_summary(
    session: SessionDep,
    settings: SettingsDep,
    client: CurrentClient,
    _model: LlmModelDep,  # 503 before any job exists when AI is not configured
    enqueue: JobEnqueuerDep,
    data: Annotated[SummaryGenerate, Body()],
    idempotency_key: Annotated[
        str | None, Header(min_length=1, max_length=128, pattern=r"^[!-~]+$")
    ] = None,
) -> SummaryJobRead:
    """Queues generation of a private AI *draft* from the client's own entries in the period and
    returns the job at once. Repeating the request (same `Idempotency-Key`, or without a key
    while a job for the same period is active) returns the existing job."""
    await usage.check_daily_budget(session, settings, client)  # 429 before any job exists
    try:
        job, created = await jobs.create_or_get(
            session, client, data.period_start, data.period_end, idempotency_key
        )
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    if created:
        try:
            enqueue(job.id)
        except Exception as exc:
            logger.error("could not enqueue summary job", extra={"error_type": type(exc).__name__})
            await jobs.fail_queued(session, job.id, "enqueue_failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Background processing is not available"
            ) from None
    return SummaryJobRead.model_validate(job)


@router.get("/summaries/jobs/{job_id}")
async def get_summary_job(
    session: SessionDep, client: CurrentClient, job_id: uuid.UUID
) -> SummaryJobRead:
    try:
        job = await jobs.get_own(session, client, job_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from None
    read = SummaryJobRead.model_validate(job)
    if job.status == SummaryJobStatus.CRISIS:
        read.crisis = _CRISIS
    return read


@router.post(
    "/after-session-notes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_per_user("after_session"))],
)
async def create_after_session_note(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    client: CurrentClient,
    model: LlmModelDep,
    data: Annotated[AfterSessionCreate, Body()],
) -> AfterSessionRead | CrisisResponse:
    await usage.check_daily_budget(session, settings, client)
    try:
        note = await service.create_after_session_note(session, settings, model, client, data.text)
    except CrisisDetectedError:
        response.status_code = status.HTTP_200_OK  # not a created resource
        return _CRISIS
    except AiGenerationError as exc:
        raise _generation_failed(exc) from None
    return AfterSessionRead.model_validate(note)


@router.get("/after-session-notes")
async def list_after_session_notes(
    session: SessionDep, client: CurrentClient
) -> list[AfterSessionRead]:
    notes = await service.list_after_session_notes(session, client)
    return [AfterSessionRead.model_validate(n) for n in notes]
