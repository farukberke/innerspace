import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class AppointmentKind(StrEnum):
    THERAPY = "therapy"
    PSYCHIATRY = "psychiatry"


class Appointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client's upcoming or past appointment, optionally with a clinician of the same clinic."""

    __tablename__ = "appointments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["clinician_id", "organization_id"],
            ["users.id", "users.organization_id"],
            # No cascade: a clinician with appointments must be reassigned before removal.
        ),
        Index("ix_appointments_client_id_scheduled_at", "client_id", "scheduled_at"),
    )

    organization_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    clinician_id: Mapped[uuid.UUID | None]
    kind: Mapped[AppointmentKind] = mapped_column(str_enum(AppointmentKind, "appointment_kind"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
