import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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


class SummaryStatus(StrEnum):
    DRAFT = "draft"  # AI output (or edited since); private, not yet approved
    APPROVED = "approved"  # the client reviewed it; still private
    SHARED = "shared"  # visible to the assigned clinician
    REVOKED = "revoked"  # was shared, the client took it back


class Summary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client's summary for their clinician. Private until the client shares it.

    Lifecycle (human-in-the-loop): draft -> approved -> shared <-> revoked. Only the client
    moves it; editing returns it to draft. `body` is rendered from the statements.
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
    status: Mapped[SummaryStatus] = mapped_column(
        str_enum(SummaryStatus, "summary_status"), default=SummaryStatus.DRAFT
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    statements: Mapped[list["SummaryStatement"]] = relationship(
        order_by="SummaryStatement.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SummaryJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CRISIS = "crisis"  # crisis language found: nothing generated, fixed crisis response shown


class SummaryJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Background summary generation for one client and period. Holds no content: failures are
    recorded as a short `error_code` only.

    Idempotency: an explicit `idempotency_key` is unique per client; without a key at most one
    queued/running job per client and period exists (partial unique index).
    """

    __tablename__ = "summary_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("client_id", "idempotency_key", name="uq_summary_jobs_idempotency"),
        Index(
            "uq_summary_jobs_active_period",
            "client_id",
            "period_start",
            "period_end",
            unique=True,
            postgresql_where=text("idempotency_key IS NULL AND status IN ('queued', 'running')"),
        ),
    )

    organization_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[SummaryJobStatus] = mapped_column(
        str_enum(SummaryJobStatus, "summary_job_status"), default=SummaryJobStatus.QUEUED
    )
    summary_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("summaries.id", ondelete="SET NULL")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))


class SummaryStatement(UUIDPrimaryKeyMixin, Base):
    """One statement of a summary, with the entries it is based on."""

    __tablename__ = "summary_statements"
    __table_args__ = (Index("ix_summary_statements_summary_id", "summary_id"),)

    summary_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("summaries.id", ondelete="CASCADE"))
    position: Mapped[int]
    section: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)

    citations: Mapped[list["SummaryCitation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class SummaryCitation(Base):
    """Statement -> source entry. Deleting an entry removes the citation, not the statement."""

    __tablename__ = "summary_citations"

    statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("summary_statements.id", ondelete="CASCADE"), primary_key=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class AfterSessionNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The client's post-session free text, structured by AI. Visible only to the client."""

    __tablename__ = "after_session_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            ondelete="CASCADE",
        ),
        Index("ix_after_session_notes_client_id_created_at", "client_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID]
    client_id: Mapped[uuid.UUID]
    source_text: Mapped[str] = mapped_column(Text)
    discussed: Mapped[list[str]] = mapped_column(JSONB, default=list)
    to_try: Mapped[list[str]] = mapped_column(JSONB, default=list)
    questions: Mapped[list[str]] = mapped_column(JSONB, default=list)


class LlmUsage(UUIDPrimaryKeyMixin, Base):
    """Token/cost/latency record per LLM call. Never holds prompts or any user content."""

    __tablename__ = "llm_usage"
    __table_args__ = (
        Index("ix_llm_usage_organization_id_created_at", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None]
    purpose: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    requests: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    duration_ms: Mapped[int]
    success: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
