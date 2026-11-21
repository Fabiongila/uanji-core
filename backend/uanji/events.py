"""Barramento de eventos de domínio, processado depois do commit.

Os serviços chamam ``publish(db, ...)`` dentro da transacção. Os eventos só são
entregues aos subscritores depois de a transacção ser confirmada, garantindo que
as automações nunca reagem a dados que acabaram por ser revertidos.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

Handler = Callable[[str, dict[str, Any]], None]
_handlers: dict[str, list[Handler]] = {}


def subscribe(name: str, handler: Handler) -> None:
    _handlers.setdefault(name, []).append(handler)


def clear_handlers() -> None:
    _handlers.clear()


def publish(db: Session, name: str, payload: dict[str, Any]) -> None:
    db.info.setdefault("pending_events", []).append((name, payload))


@sa_event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    pending = session.info.pop("pending_events", [])
    for name, payload in pending:
        for handler in _handlers.get(name, []):
            try:
                handler(name, payload)
            except Exception:
                log.exception("Falha num subscritor do evento %s", name)


@sa_event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("pending_events", None)
