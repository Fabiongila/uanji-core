"""Estado de execução partilhado (base de dados activa e definições)."""

from __future__ import annotations

from .config import Settings
from .db import Database

_database: Database | None = None
_settings: Settings | None = None


def init(database: Database, settings: Settings) -> None:
    global _database, _settings
    _database = database
    _settings = settings


def get_database() -> Database:
    if _database is None:
        raise RuntimeError("Base de dados não inicializada")
    return _database


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Definições não inicializadas")
    return _settings
