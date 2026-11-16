import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response, status

from app.ai.crisis import CRISIS_MESSAGE, CRISIS_RESOURCES
from app.ai.llm import AiGenerationError
from app.api.deps import CurrentClient, LlmModelDep, SessionDep, SettingsDep
from app.schemas.care import (
    AfterSessionCreate,
    AfterSessionRead,
    CrisisResponse,
    SummaryGenerate,
    SummaryRead,
)
from app.services import ai as service
from app.services.errors import CrisisDetectedError, ValidationFailedError

router = APIRouter(tags=["ai"])
logger = logging.getLogger(__name__)

_CRISIS = CrisisResponse(message=CRISIS_MESSAGE, resources=CRISIS_RESOURCES)


def _generation_failed(exc: AiGenerationError) -> HTTPException:
    logger.warning("ai generation failed", extra={"error_type": str(exc)})
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        "Could not produce a safe result right now. Please try again later.",
    )


@router.post("/summaries/generate", status_code=status.HTTP_201_CREATED)
async def generate_summary(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    client: CurrentClient,
    model: LlmModelDep,
    data: Annotated[SummaryGenerate, Body()],
) -> SummaryRead | CrisisResponse:
    """Creates a private AI *draft* from the client's own entries in the period. If crisis
    language is found nothing is generated and a fixed crisis response (HTTP 200) is returned."""
    try:
        summary = await service.generate_summary(
            session, settings, model, client, data.period_start, data.period_end
        )
    except CrisisDetectedError:
        response.status_code = status.HTTP_200_OK  # not a created resource
        return _CRISIS
    except ValidationFailedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None
    except AiGenerationError as exc:
        raise _generation_failed(exc) from None
    return SummaryRead.from_model(summary)


@router.post("/after-session-notes", status_code=status.HTTP_201_CREATED)
async def create_after_session_note(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    client: CurrentClient,
    model: LlmModelDep,
    data: Annotated[AfterSessionCreate, Body()],
) -> AfterSessionRead | CrisisResponse:
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
