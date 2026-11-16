"""appointment authorship, summary-appointment link, support plans (additive only)

Revision ID: d4e5f6071829
Revises: c3d4e5f60718
Create Date: 2026-11-17 01:46:24.647960

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6071829"
down_revision: str | Sequence[str] | None = "c3d4e5f60718"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "support_plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("moment_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("self_note", sa.String(length=500), nullable=False),
        sa.Column("contacts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warning_signs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coping_strategies", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("talk_to_clinician", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["client_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name=op.f("fk_support_plans_client_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_plans")),
        sa.UniqueConstraint("client_id", name="uq_support_plans_client_id"),
    )
    op.add_column("appointments", sa.Column("created_by_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_appointments_created_by_id_users"),
        "appointments",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for table in ("summaries", "summary_jobs"):
        op.add_column(table, sa.Column("appointment_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_appointment_id_appointments"),
            table,
            "appointments",
            ["appointment_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in ("summary_jobs", "summaries"):
        op.drop_constraint(
            op.f(f"fk_{table}_appointment_id_appointments"), table, type_="foreignkey"
        )
        op.drop_column(table, "appointment_id")
    op.drop_constraint(
        op.f("fk_appointments_created_by_id_users"), "appointments", type_="foreignkey"
    )
    op.drop_column("appointments", "created_by_id")
    op.drop_table("support_plans")
