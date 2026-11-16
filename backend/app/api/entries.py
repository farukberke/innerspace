import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import AwareDatetime

from app.api.deps import CurrentClient, SessionDep
from app.models import EntryKind
from app.schemas.entry import EntryCreate, EntryPage, EntryRead, EntryUpdate
from app.services import entries as service

router = APIRouter(prefix="/entries", tags=["entries"])


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_entry(
    session: SessionDep, client: CurrentClient, data: Annotated[EntryCreate, Body()]
) -> EntryRead:
    entry = await service.create_entry(session, client, data)
    return EntryRead.model_validate(entry)


@router.get("")
async def list_entries(
    session: SessionDep,
    client: CurrentClient,
    kind: EntryKind | None = None,
    occurred_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntryPage:
    items, total = await service.list_entries(
        session,
        client,
        kind=kind,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
        offset=offset,
    )
    return EntryPage(
        items=[EntryRead.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{entry_id}")
async def get_entry(session: SessionDep, client: CurrentClient, entry_id: uuid.UUID) -> EntryRead:
    try:
        entry = await service.get_entry(session, client, entry_id)
    except service.EntryNotFoundError:
        raise _not_found() from None
    return EntryRead.model_validate(entry)


@router.patch("/{entry_id}")
async def update_entry(
    session: SessionDep, client: CurrentClient, entry_id: uuid.UUID, data: EntryUpdate
) -> EntryRead:
    try:
        entry = await service.update_entry(session, client, entry_id, data)
    except service.EntryNotFoundError:
        raise _not_found() from None
    except service.EntryValidationError as exc:
        raise RequestValidationError(exc.errors) from None
    return EntryRead.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(session: SessionDep, client: CurrentClient, entry_id: uuid.UUID) -> Response:
    try:
        await service.delete_entry(session, client, entry_id)
    except service.EntryNotFoundError:
        raise _not_found() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
