"""indexes for the daily LLM budget check and the stale-job reaper

Revision ID: b7c2d9e04a11
Revises: a1181e88dde4
Create Date: 2026-11-17 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c2d9e04a11"
down_revision: str | Sequence[str] | None = "a1181e88dde4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_llm_usage_user_id_created_at", "llm_usage", ["user_id", "created_at"])
    op.create_index(
        "ix_summary_jobs_running_updated_at",
        "summary_jobs",
        ["updated_at"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_summary_jobs_running_updated_at",
        table_name="summary_jobs",
        postgresql_where=sa.text("status = 'running'"),
    )
    op.drop_index("ix_llm_usage_user_id_created_at", table_name="llm_usage")
