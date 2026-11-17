"""Entry API schemas.

Each entry kind has its own `details` shape. Create requests are a discriminated union on
`kind`; the kind cannot change after creation.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

from app.models.entry import EntryKind

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Intensity = Annotated[int, Field(ge=0, le=10)]

# Small tolerance for client clock skew; entries describe things that already happened.
_FUTURE_TOLERANCE = timedelta(minutes=5)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Kind-specific details -------------------------------------------------------------


class QuickDetails(_Strict):
    mood: Annotated[int, Field(ge=1, le=5)] | None = None
    # Last night's sleep as the client remembers it, in half-hour steps.
    sleep_hours: Annotated[float, Field(ge=0, le=24, multiple_of=0.5)] | None = None


class PanicDetails(_Strict):
    intensity: Intensity
    duration_minutes: Annotated[int, Field(ge=0, le=24 * 60)] | None = None
    symptoms: Annotated[list[ShortText], Field(max_length=20)] = []
    trigger: ShortText | None = None


class MedicationDetails(_Strict):
    """The client's own record of what they took. The app never recommends medication."""

    medication_name: ShortText
    taken: bool
    side_effects: Annotated[list[ShortText], Field(max_length=20)] = []


class AvoidanceDetails(_Strict):
    situation: ShortText
    avoided: bool
    anxiety: Intensity | None = None


DETAILS_BY_KIND: dict[EntryKind, TypeAdapter[Any]] = {
    EntryKind.QUICK: TypeAdapter(QuickDetails),
    EntryKind.PANIC: TypeAdapter(PanicDetails),
    EntryKind.MEDICATION: TypeAdapter(MedicationDetails),
    EntryKind.AVOIDANCE: TypeAdapter(AvoidanceDetails),
}


# --- Requests --------------------------------------------------------------------------


def _ensure_not_future(value: datetime | None) -> datetime | None:
    if value is not None and value > datetime.now(UTC) + _FUTURE_TOLERANCE:
        raise ValueError("occurred_at cannot be in the future")
    return value


class _EntryCreateBase(_Strict):
    occurred_at: AwareDatetime
    note: Note | None = None

    _check_occurred_at = field_validator("occurred_at")(_ensure_not_future)


class QuickEntryCreate(_EntryCreateBase):
    kind: Literal[EntryKind.QUICK]
    details: QuickDetails = QuickDetails()

    @field_validator("note")
    @classmethod
    def _note_required(cls, value: str | None) -> str | None:
        if not value:
            raise ValueError("a quick entry needs a note")
        return value


class PanicEntryCreate(_EntryCreateBase):
    kind: Literal[EntryKind.PANIC]
    details: PanicDetails


class MedicationEntryCreate(_EntryCreateBase):
    kind: Literal[EntryKind.MEDICATION]
    details: MedicationDetails


class AvoidanceEntryCreate(_EntryCreateBase):
    kind: Literal[EntryKind.AVOIDANCE]
    details: AvoidanceDetails


EntryCreate = Annotated[
    QuickEntryCreate | PanicEntryCreate | MedicationEntryCreate | AvoidanceEntryCreate,
    Field(discriminator="kind"),
]


class EntryUpdate(_Strict):
    """Partial update. `details`, if given, replaces the whole object and is validated
    against the entry's existing kind."""

    occurred_at: AwareDatetime | None = None
    note: Note | None = None
    details: dict[str, Any] | None = None

    _check_occurred_at = field_validator("occurred_at")(_ensure_not_future)


# --- Responses -------------------------------------------------------------------------


class EntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: EntryKind
    occurred_at: datetime
    note: str | None
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class EntryPage(BaseModel):
    items: list[EntryRead]
    total: int
    limit: int
    offset: int
