import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status

from app.api.deps import CurrentClient, CurrentClinician, SessionDep
from app.schemas.care import ClientRead, SummaryCreate, SummaryRead
from app.services import people
from app.services import summaries as service
from app.services.errors import NotFoundError

router = APIRouter(tags=["summaries"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Summary not found")


# --- Client: own summaries, and the sharing (approval) decision ------------------------


@router.post("/summaries", status_code=status.HTTP_201_CREATED)
async def create_summary(
    session: SessionDep, client: CurrentClient, data: Annotated[SummaryCreate, Body()]
) -> SummaryRead:
    summary = await service.create_summary(session, client, data.title, data.body)
    return SummaryRead.model_validate(summary)


@router.get("/summaries")
async def list_summaries(session: SessionDep, client: CurrentClient) -> list[SummaryRead]:
    return [SummaryRead.model_validate(s) for s in await service.list_own(session, client)]


@router.get("/summaries/{summary_id}")
async def get_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        return SummaryRead.model_validate(await service.get_own(session, client, summary_id))
    except NotFoundError:
        raise _not_found() from None


@router.post("/summaries/{summary_id}/share")
async def share_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.set_shared(session, client, summary_id, True)
    except NotFoundError:
        raise _not_found() from None
    return SummaryRead.model_validate(summary)


@router.post("/summaries/{summary_id}/unshare")
async def unshare_summary(
    session: SessionDep, client: CurrentClient, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.set_shared(session, client, summary_id, False)
    except NotFoundError:
        raise _not_found() from None
    return SummaryRead.model_validate(summary)


# --- Clinician: assigned clients and the summaries they have shared --------------------


@router.get("/clinician/clients")
async def list_clients(session: SessionDep, clinician: CurrentClinician) -> list[ClientRead]:
    clients = await people.list_assigned_clients(session, clinician)
    return [ClientRead.model_validate(c) for c in clients]


@router.get("/clinician/summaries")
async def list_shared_summaries(
    session: SessionDep, clinician: CurrentClinician
) -> list[SummaryRead]:
    items = await service.list_shared_with(session, clinician)
    return [SummaryRead.model_validate(s) for s in items]


@router.get("/clinician/summaries/{summary_id}")
async def get_shared_summary(
    session: SessionDep, clinician: CurrentClinician, summary_id: uuid.UUID
) -> SummaryRead:
    try:
        summary = await service.get_shared_with(session, clinician, summary_id)
    except NotFoundError:
        raise _not_found() from None
    return SummaryRead.model_validate(summary)
