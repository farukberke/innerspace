"""summary reads: when a clinician last opened a shared summary (additive only)

Revision ID: f60718293a4b
Revises: e5f607182930
Create Date: 2026-11-20 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f60718293a4b"
down_revision: str | Sequence[str] | None = "e5f607182930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "summary_reads",
        sa.Column("summary_id", sa.Uuid(), nullable=False),
        sa.Column("clinician_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["summaries.id"],
            name=op.f("fk_summary_reads_summary_id_summaries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["clinician_id", "organization_id"],
            ["users.id", "users.organization_id"],
            name=op.f("fk_summary_reads_clinician_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("summary_id", "clinician_id", name=op.f("pk_summary_reads")),
    )


def downgrade() -> None:
    op.drop_table("summary_reads")
