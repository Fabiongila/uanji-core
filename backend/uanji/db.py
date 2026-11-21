"""Motor SQLite, sessões e utilitários de migração."""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from alembic import command

log = logging.getLogger(__name__)

# Em executáveis PyInstaller, os ficheiros de migração estão em sys._MEIPASS.
BACKEND_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragmas(dbapi_conn: sqlite3.Connection, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


class Database:
    """Mantém o motor e a fábrica de sessões. Pode ser reaberto (ex.: após restauro)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = make_engine(url)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

    def reopen(self) -> None:
        self.engine.dispose()
        self.engine = make_engine(self.url)
        self.SessionLocal.configure(bind=self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()


def fts5_available(engine: Engine) -> bool:
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        assert raw is not None
        try:
            raw.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._fts_probe USING fts5(x)")
            raw.execute("DROP TABLE temp._fts_probe")
            return True
        except sqlite3.OperationalError:
            return False


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    # Mantém a configuração de logs da aplicação (JSON + redacção).
    cfg.attributes["configure_logger"] = False
    return cfg


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def head_revision(url: str) -> str | None:
    return ScriptDirectory.from_config(alembic_config(url)).get_current_head()


def upgrade_to_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")
