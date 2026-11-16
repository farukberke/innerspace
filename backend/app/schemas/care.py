import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import Summary, SummaryJobStatus, SummaryStatus, UserRole
from app.schemas.planning import PlanContact

MAX_PERIOD_DAYS = 92

# Deliberately loose: real validation of ownership happens by sending the invite.
Email = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)]
Password = Annotated[str, Field(min_length=12, max_length=128)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=128)]


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1, max_length=4096)]


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool


class ClientRead(BaseModel):
    """What a clinician sees about an assigned client: identity only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    # The client's next clinic appointment with the requesting clinician (list endpoint only).
    next_appointment_at: datetime | None = None


class InvitationCreate(BaseModel):
    email: Email
    role: UserRole = UserRole.CLIENT
    # Org admin only: assign an invited client to this clinician.
    clinician_id: uuid.UUID | None = None


class InvitationCreated(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    expires_at: datetime
    # Shown exactly once. E-mail delivery is out of scope for now.
    token: str


class InvitationAccept(BaseModel):
    token: Annotated[str, Field(min_length=1, max_length=256)]
    password: Password
    display_name: DisplayName


class UserStatusUpdate(BaseModel):
    is_active: bool


class AssignmentCreate(BaseModel):
    clinician_id: uuid.UUID
    client_id: uuid.UUID


class AssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinician_id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


class SummaryGenerate(BaseModel):
    """Period (inclusive dates, UTC) whose entries the summary is based on. With an
    `appointment_id` the period may be omitted: it then runs from the client's previous
    appointment to that one."""

    period_start: date | None = None
    period_end: date | None = None
    appointment_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_period(self) -> Self:
        if self.period_start is None and self.period_end is None:
            if self.appointment_id is None:
                raise ValueError("period_start and period_end (or appointment_id) are required")
            return self
        if self.period_start is None or self.period_end is None:
            raise ValueError("period_start and period_end must be given together")
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        if (self.period_end - self.period_start).days > MAX_PERIOD_DAYS:
            raise ValueError(f"period must not exceed {MAX_PERIOD_DAYS} days")
        return self


class StatementEdit(BaseModel):
    id: uuid.UUID
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class SummaryUpdate(BaseModel):
    """Client edits of a draft. Editing returns the summary to `draft` (re-approval needed)."""

    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    statements: Annotated[list[StatementEdit], Field(max_length=100)] = []


class StatementRead(BaseModel):
    id: uuid.UUID
    section: str
    text: str
    source_entry_ids: list[uuid.UUID]


class SummaryRead(BaseModel):
    """The client's view: includes status and the entries each statement is based on."""

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    body: str
    status: SummaryStatus
    period_start: date | None
    period_end: date | None
    statements: list[StatementRead]
    approved_at: datetime | None
    shared_at: datetime | None
    created_at: datetime
    appointment_id: uuid.UUID | None = None

    @classmethod
    def from_model(cls, summary: Summary) -> Self:
        return cls(
            id=summary.id,
            client_id=summary.client_id,
            title=summary.title,
            body=summary.body,
            status=summary.status,
            period_start=summary.period_start,
            period_end=summary.period_end,
            statements=[
                StatementRead(
                    id=st.id,
                    section=st.section,
                    text=st.text,
                    source_entry_ids=sorted(c.entry_id for c in st.citations),
                )
                for st in summary.statements
            ],
            approved_at=summary.approved_at,
            shared_at=summary.shared_at,
            created_at=summary.created_at,
            appointment_id=summary.appointment_id,
        )


class SummaryListItem(BaseModel):
    """Clinician list: metadata only; the body is returned (and audited) by the detail endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    period_start: date | None
    period_end: date | None
    shared_at: datetime | None
    created_at: datetime


class SharedSummaryRead(SummaryListItem):
    """Clinician detail. Deliberately no citations: the client's raw entries stay private."""

    body: str


class CrisisResponse(BaseModel):
    crisis: bool = True
    message: str
    resources: list[dict[str, str]]
    # The client's own "Planım" contacts (only theirs); the fixed message above never changes.
    contacts: list[PlanContact] = []


class AfterSessionCreate(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class AfterSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    discussed: list[str]
    to_try: list[str]
    questions: list[str]
    created_at: datetime


class SummaryJobRead(BaseModel):
    """Status of a background summary generation. Never contains content."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SummaryJobStatus
    period_start: date
    period_end: date
    summary_id: uuid.UUID | None
    appointment_id: uuid.UUID | None = None
    error_code: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime
    crisis: CrisisResponse | None = None  # set (fixed text) when status is "crisis"
