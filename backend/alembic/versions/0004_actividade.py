"""actividade no computador

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import uanji.models

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app", sa.String(length=200), nullable=False),
        sa.Column("bundle_id", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("context", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", uanji.models.UTCDateTime(), nullable=False),
        sa.Column("ended_at", uanji.models.UTCDateTime(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("activity_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_activity_sessions_app", ["app"], unique=False)
        batch_op.create_index("ix_activity_sessions_category", ["category"], unique=False)
        batch_op.create_index("ix_activity_sessions_project_id", ["project_id"], unique=False)
        batch_op.create_index("ix_activity_sessions_started_at", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_table("activity_sessions")
