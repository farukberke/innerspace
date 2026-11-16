"""Schemas for appointments and the support plan ("Planım")."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.models import AppointmentKind


class AppointmentCreate(BaseModel):
    kind: AppointmentKind
    scheduled_at: AwareDatetime


class AppointmentUpdate(BaseModel):
    kind: AppointmentKind | None = None
    scheduled_at: AwareDatetime | None = None


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    clinician_id: uuid.UUID | None
    clinician_name: str | None = None
    kind: AppointmentKind
    scheduled_at: datetime


# --- Support plan ------------------------------------------------------------------------

PlanItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Digits and common phone punctuation only: the value ends up in a `tel:` link.
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ()\-]{3,32}$")]


class PlanContact(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    phone: Phone


class PlanContent(BaseModel):
    moment_steps: Annotated[list[PlanItem], Field(max_length=10)] = []
    self_note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    contacts: Annotated[list[PlanContact], Field(max_length=8)] = []
    warning_signs: Annotated[list[PlanItem], Field(max_length=10)] = []
    coping_strategies: Annotated[list[PlanItem], Field(max_length=10)] = []
    talk_to_clinician: Annotated[list[PlanItem], Field(max_length=10)] = []


class PlanRead(PlanContent):
    """The client's own view. `shared_at` is set while the plan is shared with the clinician."""

    model_config = ConfigDict(from_attributes=True)

    shared_at: datetime | None = None
    updated_at: datetime | None = None


class SharedPlanRead(PlanContent):
    """Clinician view of a shared plan (read-only)."""

    model_config = ConfigDict(from_attributes=True)

    shared_at: datetime
    updated_at: datetime
