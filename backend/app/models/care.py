import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.user import UserRole


class CareAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Clinician-client pairing inside one organization. Managed by the org admin only."""

    __tablename__ = "care_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinician_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("clinician_id", "client_id", name="uq_care_assignments_pair"),
        Index("ix_care_assignments_client_id", "client_id"),
    )

    organization_id: Mapped[uuid.UUID]
    clinician_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]


class Invitation(UUIDPrimaryKeyMixin, Base):
    """Single-use, expiring invitation. Only the SHA-256 hash of the token is stored."""

    __tablename__ = "invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invited_by_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["assign_clinician_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    invited_by_id: Mapped[uuid.UUID]
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "invitation_role"))
    # For client invitations: the clinician the new client is assigned to on acceptance.
    assign_clinician_id: Mapped[uuid.UUID | None]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Summary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client's summary for their clinician. Private until the client shares it.

    Phase 3 fills `body` from AI drafts; sharing is the client's approval step and can be
    revoked (`shared_at` back to NULL).
    """

    __tablename__ = "summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        Index("ix_summaries_client_id_created_at", "client_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of security-relevant actions. Never holds clinical content or PII."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),
    )

    # Deliberately no foreign keys: the log must outlive the rows it refers to.
    organization_id: Mapped[uuid.UUID | None]
    actor_id: Mapped[uuid.UUID | None]
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID | None]
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
