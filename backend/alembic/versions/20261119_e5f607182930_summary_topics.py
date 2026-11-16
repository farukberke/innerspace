"""summary topics: the client's own "topics to talk about" (additive only)

Revision ID: e5f607182930
Revises: d4e5f6071829
Create Date: 2026-11-19 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f607182930"
down_revision: str | Sequence[str] | None = "d4e5f6071829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "summaries",
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("summaries", "topics")
