import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import UserRole

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


class SummaryCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class SummaryListItem(BaseModel):
    """Metadata only: the body is returned (and audited) by the detail endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    shared_at: datetime | None
    created_at: datetime


class SummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    title: str
    body: str
    shared_at: datetime | None
    created_at: datetime
