"""desempenho, objectivos, versões, código e gatilhos externos

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import uanji.models

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", uanji.models.UTCDateTime(), nullable=False),
        sa.Column("updated_at", uanji.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_project_id", "goals", ["project_id"])
    op.create_table(
        "project_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("released_at", uanji.models.UTCDateTime(), nullable=True),
        sa.Column("git_tag", sa.String(length=100), nullable=False),
        sa.Column("created_at", uanji.models.UTCDateTime(), nullable=False),
        sa.Column("updated_at", uanji.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    op.create_index("ix_project_versions_project_id", "project_versions", ["project_id"])
    op.create_table(
        "code_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("repo", sa.String(length=200), nullable=False),
        sa.Column("ref", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False),
        sa.Column("happened_at", uanji.models.UTCDateTime(), nullable=True),
        sa.Column("created_at", uanji.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "kind", "repo", "ref"),
    )
    op.create_index("ix_code_links_task_id", "code_links", ["task_id"])
    with op.batch_alter_table("tasks", schema=None) as b:
        b.add_column(sa.Column("number", sa.Integer(), nullable=True))
        b.add_column(sa.Column("started_at", uanji.models.UTCDateTime(), nullable=True))
        b.add_column(sa.Column("blocked_at", uanji.models.UTCDateTime(), nullable=True))
        b.add_column(sa.Column("blocked_seconds", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("goal_id", sa.String(length=36), nullable=True))
        b.add_column(sa.Column("version_id", sa.String(length=36), nullable=True))
        b.create_index("ix_tasks_number", ["number"])
        b.create_index("ix_tasks_goal_id", ["goal_id"])
        b.create_index("ix_tasks_version_id", ["version_id"])
        b.create_foreign_key("fk_tasks_goal_id", "goals", ["goal_id"], ["id"], ondelete="SET NULL")
        b.create_foreign_key("fk_tasks_version_id", "project_versions", ["version_id"], ["id"], ondelete="SET NULL")
    with op.batch_alter_table("automations", schema=None) as b:
        b.add_column(sa.Column("webhook_secret_hash", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("trigger_state", sa.JSON(), nullable=False, server_default="{}"))
    # Numeração das tarefas existentes por ordem de criação; tarefas bloqueadas começam a contar agora.
    bind = op.get_bind()
    rows = bind.exec_driver_sql("SELECT id FROM tasks ORDER BY created_at, id").fetchall()
    for i, (tid,) in enumerate(rows, start=1):
        bind.exec_driver_sql("UPDATE tasks SET number = ? WHERE id = ?", (i, tid))
    bind.exec_driver_sql(
        "UPDATE tasks SET blocked_at = updated_at WHERE status = 'blocked' AND blocked_at IS NULL"
    )
    bind.exec_driver_sql(
        "UPDATE tasks SET started_at = updated_at WHERE status = 'in_progress' AND started_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("automations", schema=None) as b:
        b.drop_column("trigger_state")
        b.drop_column("webhook_secret_hash")
    with op.batch_alter_table("tasks", schema=None) as b:
        b.drop_constraint("fk_tasks_version_id", type_="foreignkey")
        b.drop_constraint("fk_tasks_goal_id", type_="foreignkey")
        b.drop_index("ix_tasks_version_id")
        b.drop_index("ix_tasks_goal_id")
        b.drop_index("ix_tasks_number")
        for c in ("version_id", "goal_id", "blocked_seconds", "blocked_at", "started_at", "number"):
            b.drop_column(c)
    op.drop_table("code_links")
    op.drop_table("project_versions")
    op.drop_table("goals")
