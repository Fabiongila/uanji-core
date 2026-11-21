"""Dependências partilhadas pelos routers."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import Database
from ..errors import AppError


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def require_token(request: Request) -> None:
    """Exige o token partilhado com o processo desktop (cabeçalho Authorization: Bearer)."""
    settings: Settings = request.app.state.settings
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(value.encode(), settings.token.encode()):
        raise Unauthorized("Token de acesso ao backend em falta ou inválido.")


def get_db(database: Database = Depends(get_database)) -> Iterator[Session]:
    s = database.SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# Sessão confirmada ANTES de a resposta ser enviada (um erro de commit nunca é
# reportado ao cliente como sucesso).
DB = Annotated[Session, Depends(get_db, scope="function")]
