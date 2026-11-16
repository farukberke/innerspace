"""Entry business logic. Every query is scoped to the owning client and their organization."""

import uuid
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entry, EntryKind, User
from app.schemas.entry import DETAILS_BY_KIND, EntryCreate, EntryUpdate


class EntryNotFoundError(Exception):
    pass


class EntryValidationError(Exception):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        super().__init__("invalid entry")
        self.errors = errors


def _owned_by(client: User) -> Select[tuple[Entry]]:
    return select(Entry).where(
        Entry.client_id == client.id,
        Entry.organization_id == client.organization_id,
    )


async def create_entry(session: AsyncSession, client: User, data: EntryCreate) -> Entry:
    entry = Entry(
        organization_id=client.organization_id,
        client_id=client.id,
        kind=data.kind,
        occurred_at=data.occurred_at,
        note=data.note or None,
        details=data.details.model_dump(mode="json"),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_entries(
    session: AsyncSession,
    client: User,
    *,
    kind: EntryKind | None,
    occurred_from: datetime | None,
    occurred_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[list[Entry], int]:
    query = _owned_by(client)
    if kind is not None:
        query = query.where(Entry.kind == kind)
    if occurred_from is not None:
        query = query.where(Entry.occurred_at >= occurred_from)
    if occurred_to is not None:
        query = query.where(Entry.occurred_at < occurred_to)

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(Entry.occurred_at.desc(), Entry.id.desc()).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def get_entry(session: AsyncSession, client: User, entry_id: uuid.UUID) -> Entry:
    # Another client's entry is indistinguishable from a missing one (no existence leak).
    entry = await session.scalar(_owned_by(client).where(Entry.id == entry_id))
    if entry is None:
        raise EntryNotFoundError
    return entry


async def update_entry(
    session: AsyncSession, client: User, entry_id: uuid.UUID, data: EntryUpdate
) -> Entry:
    entry = await get_entry(session, client, entry_id)
    changes = data.model_dump(exclude_unset=True)

    if "occurred_at" in changes:
        if changes["occurred_at"] is None:
            raise EntryValidationError([_error("occurred_at", "occurred_at cannot be null")])
        entry.occurred_at = changes["occurred_at"]
    if "details" in changes:
        if changes["details"] is None:
            raise EntryValidationError([_error("details", "details cannot be null")])
        try:
            details = DETAILS_BY_KIND[entry.kind].validate_python(changes["details"])
        except ValidationError as exc:
            raise EntryValidationError(
                [_error(("details", *e["loc"]), e["msg"]) for e in exc.errors()]
            ) from exc
        entry.details = details.model_dump(mode="json")
    if "note" in changes:
        entry.note = changes["note"] or None
    if entry.kind == EntryKind.QUICK and not entry.note:
        raise EntryValidationError([_error("note", "a quick entry needs a note")])

    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_entry(session: AsyncSession, client: User, entry_id: uuid.UUID) -> None:
    entry = await get_entry(session, client, entry_id)
    await session.delete(entry)
    await session.commit()


def _error(loc: str | tuple[object, ...], msg: str) -> dict[str, object]:
    loc_tuple = (loc,) if isinstance(loc, str) else loc
    return {"loc": ["body", *loc_tuple], "msg": msg, "type": "value_error"}


def entries_in_period(
    client_id: uuid.UUID, organization_id: uuid.UUID, start: datetime, end: datetime
) -> Select[tuple[Entry]]:
    """Entries of one client within [start, end). Used by the AI tools and validators, which
    receive the client from the authenticated request, never from the model."""
    return select(Entry).where(
        Entry.client_id == client_id,
        Entry.organization_id == organization_id,
        Entry.occurred_at >= start,
        Entry.occurred_at < end,
    )
