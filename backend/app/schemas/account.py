"""Schemas for the client's data rights (export, account deletion) and in-app reminders."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole
from app.schemas.care import SummaryRead
from app.schemas.entry import EntryRead
from app.schemas.planning import AppointmentRead, PlanRead


class AccountDelete(BaseModel):
    """Both the password and the typed confirmation word are required."""

    password: Annotated[str, Field(min_length=1, max_length=128)]
    confirmation: Literal["SİL"]


class ExportProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    created_at: datetime


class ExportAfterSessionNote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_text: str
    discussed: list[str]
    to_try: list[str]
    questions: list[str]
    created_at: datetime


class AccountExport(BaseModel):
    exported_at: datetime
    profile: ExportProfile
    entries: list[EntryRead]
    summaries: list[SummaryRead]
    after_session_notes: list[ExportAfterSessionNote]
    plan: PlanRead | None
    appointments: list[AppointmentRead]


class Reminder(BaseModel):
    kind: Literal["prepare_summary", "after_session_note"]
    message: str
    appointment_id: uuid.UUID
    scheduled_at: datetime


REMINDER_MESSAGES = {
    "prepare_summary": "Yarın randevun var — hazırlanmak ister misin?",
    "after_session_note": "Dünkü seansın için kısa bir not?",
}
