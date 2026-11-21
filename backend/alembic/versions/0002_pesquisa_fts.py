"""índice de pesquisa (FTS5 com alternativa)

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        bind.exec_driver_sql(
            "CREATE VIRTUAL TABLE search_index USING fts5("
            "entity_type UNINDEXED, entity_id UNINDEXED, title, body, "
            "tokenize = 'unicode61 remove_diacritics 2')"
        )
    except Exception:
        # SQLite sem FTS5: tabela normal, pesquisada com LIKE.
        bind.exec_driver_sql(
            "CREATE TABLE search_index (entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, "
            "title TEXT NOT NULL, body TEXT NOT NULL)"
        )
        bind.exec_driver_sql("CREATE INDEX ix_search_index_entity ON search_index(entity_type, entity_id)")


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS search_index")
