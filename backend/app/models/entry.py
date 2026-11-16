import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum


class EntryKind(StrEnum):
    QUICK = "quick"
    PANIC = "panic"
    MEDICATION = "medication"
    AVOIDANCE = "avoidance"


class Entry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client's own log entry. Visible only to the client who wrote it."""

    __tablename__ = "entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        Index("ix_entries_client_id_occurred_at", "client_id", "occurred_at"),
    )

    organization_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    kind: Mapped[EntryKind] = mapped_column(str_enum(EntryKind, "entry_kind"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    # Kind-specific structured fields; shape is validated by the API schemas per `kind`.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
