import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.crisis import CRISIS_MESSAGE, CRISIS_RESOURCES
from app.api.deps import CurrentClient, CurrentClinician, SessionDep, limit_per_user
from app.models import User
from app.schemas.care import (
    ClientRead,
    CrisisResponse,
    SharedSummaryRead,
    SummaryListItem,
    SummaryRead,
    SummaryUpdate,
    TopicsUpdate,
)
from app.services import appointments, people, plans
from app.services import summaries as service
from app.services.errors import (
    ConflictError,
    CrisisDetectedError,
    NotFoundError,
    ValidationFailedError,
)

router = APIRouter(tags=["summaries"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Summary not found")


# --- Client: own summaries, and the sharing (approval) decision ------------------------


@router.get("/summaries")
async def list_summaries(session: SessionDep, client: CurrentClient) -> list[SummaryRead]:
    return [SummaryRead.from_model(s) for s in await service.list_own(session, client)]


@router.get("/summaries/{summary_id}")
async def get_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        return SummaryRead.from_model(await service.get_own(session, client, summary_id))
    except NotFoundError:
        raise _not_found() from None


@router.patch("/summaries/{summary_id}")
async def update_summary(
    session: SessionDep,
    client: CurrentClient,
    summary_id: uuid.UUID,
    data: Annotated[SummaryUpdate, Body()],
) -> SummaryRead:
    edits = {e.id: e.text for e in data.statements}
    try:
        summary = await service.update_draft(session, client, summary_id, data.title, edits)
    except NotFoundError:
        raise _not_found() from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    except ValidationFailedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None
    return SummaryRead.from_model(summary)


async def _crisis(session: AsyncSession, client: User) -> CrisisResponse:
    contacts = await plans.crisis_contacts(session, client)
    return CrisisResponse(message=CRISIS_MESSAGE, resources=CRISIS_RESOURCES, contacts=contacts)


@router.put("/summaries/{summary_id}/topics", dependencies=[Depends(limit_per_user("topics"))])
async def update_topics(
    response: Response,
    session: SessionDep,
    client: CurrentClient,
    summary_id: uuid.UUID,
    data: Annotated[TopicsUpdate, Body()],
) -> SummaryRead | CrisisResponse:
    try:
        summary = await service.set_topics(session, client, summary_id, data.topics)
    except NotFoundError:
        raise _not_found() from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    except ValidationFailedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None
    except CrisisDetectedError:
        response.status_code = status.HTTP_200_OK
        return await _crisis(session, client)
    return SummaryRead.from_model(summary)


@router.post("/summaries/{summary_id}/approve")
async def approve_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.approve(session, client, summary_id)
    except NotFoundError:
        raise _not_found() from None
    except ValidationFailedError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.message) from None
    return SummaryRead.from_model(summary)


@router.post("/summaries/{summary_id}/share")
async def share_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.set_shared(session, client, summary_id, True)
    except NotFoundError:
        raise _not_found() from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return SummaryRead.from_model(summary)


@router.post("/summaries/{summary_id}/unshare")
async def unshare_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.set_shared(session, client, summary_id, False)
    except NotFoundError:
        raise _not_found() from None
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from None
    return SummaryRead.from_model(summary)


# --- Clinician: assigned clients and the summaries they have shared --------------------


@router.get("/clinician/clients")
async def list_clients(session: SessionDep, clinician: CurrentClinician) -> list[ClientRead]:
    clients = await people.list_assigned_clients(session, clinician)
    upcoming = await appointments.next_for_clients(session, clinician, [c.id for c in clients])
    items = [ClientRead.model_validate(c) for c in clients]
    for item in items:
        item.next_appointment_at = upcoming.get(item.id)
    return items


@router.get("/clinician/summaries")
async def list_shared_summaries(
    session: SessionDep, clinician: CurrentClinician
) -> list[SummaryListItem]:
    items = await service.list_shared_with(session, clinician)
    return [SummaryListItem.model_validate(s) for s in items]


@router.get("/clinician/summaries/{summary_id}")
async def get_shared_summary(
    session: SessionDep, clinician: CurrentClinician, summary_id: uuid.UUID
) -> SharedSummaryRead:
    try:
        summary = await service.get_shared_with(session, clinician, summary_id)
    except NotFoundError:
        raise _not_found() from None
    return SharedSummaryRead.model_validate(summary)
