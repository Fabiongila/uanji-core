"""Agenda (eventos e blocos de trabalho) e revisões diárias/semanais."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..errors import ConfirmationRequired, ValidationFailed
from ..models import Activity, Event, FocusSession, Project, Review, Task, utcnow
from . import tasks as task_service
from .common import (
    day_bounds,
    get_or_404,
    index_entity,
    local_today,
    log_activity,
    unindex_entity,
    week_start,
)


def _index(db: Session, e: Event) -> None:
    index_entity(db, "event", e.id, e.title, e.description + "\n" + e.location)


def list_events(db: Session, start: datetime, end: datetime) -> list[Event]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValidationFailed("Indique o intervalo com fuso horário.")
    if end <= start:
        raise ValidationFailed("Intervalo inválido.")
    return list(db.scalars(select(Event).where(Event.start_at < end, Event.end_at > start).order_by(Event.start_at)))


def create_event(db: Session, data: schemas.EventCreate) -> Event:
    if data.project_id:
        get_or_404(db, Project, data.project_id)
    if data.task_id:
        get_or_404(db, Task, data.task_id)
    e = Event(**data.model_dump())
    db.add(e)
    db.flush()
    _index(db, e)
    log_activity(
        db, "event", e.id, "created", f"{'Bloco de trabalho' if e.kind == 'work_block' else 'Evento'} criado: {e.title}"
    )
    return e


def update_event(db: Session, event_id: str, data: schemas.EventUpdate) -> Event:
    e = get_or_404(db, Event, event_id)
    changes = data.model_dump(exclude_unset=True)
    for k in ("start_at", "end_at"):
        if k in changes and changes[k] is not None and changes[k].tzinfo is None:
            raise ValidationFailed("As datas devem incluir fuso horário.")
    for k, v in changes.items():
        setattr(e, k, v)
    if e.end_at <= e.start_at:
        raise ValidationFailed("O fim tem de ser posterior ao início.")
    db.flush()
    _index(db, e)
    return e


def delete_event(db: Session, event_id: str, confirm: bool) -> None:
    e = get_or_404(db, Event, event_id)
    if not confirm:
        raise ConfirmationRequired("Confirme a eliminação do evento.")
    unindex_entity(db, "event", e.id)
    log_activity(db, "event", e.id, "deleted", f"Evento eliminado: {e.title}")
    db.delete(e)


def agenda(db: Session, start_day: date, days: int) -> dict[str, object]:
    """Eventos + tarefas com prazo no intervalo de dias locais."""
    if not 1 <= days <= 42:
        raise ValidationFailed("O intervalo deve ter entre 1 e 42 dias.")
    start, end = day_bounds(db, start_day, days)
    events = list_events(db, start, end)
    due = db.scalars(
        select(Task).where(Task.due_at >= start, Task.due_at < end, Task.archived_at.is_(None)).order_by(Task.due_at)
    ).all()
    return {
        "start": start,
        "end": end,
        "events": [schemas.EventOut.model_validate(e) for e in events],
        "tasks": task_service.enrich(db, list(due)),
    }


# --------------------------------------------------------------------------- Revisões


def _get_or_create_review(db: Session, kind: str, period_start: date) -> Review:
    r = db.scalars(select(Review).where(Review.kind == kind, Review.period_start == period_start)).first()
    if r is None:
        r = Review(kind=kind, period_start=period_start)
        db.add(r)
        db.flush()
    return r


def normalize_period(kind: str, day: date) -> date:
    if kind == "weekly":
        return week_start(day)
    if kind == "daily":
        return day
    raise ValidationFailed("Tipo de revisão inválido.")


def review_context(db: Session, kind: str, day: date | None = None) -> schemas.ReviewContext:
    day = normalize_period(kind, day or local_today(db))
    r = _get_or_create_review(db, kind, day)
    days = 7 if kind == "weekly" else 1
    start, end = day_bounds(db, day, days)
    next_start, next_end = day_bounds(db, end.date(), days)
    completed = db.scalars(
        select(Task).where(Task.completed_at >= start, Task.completed_at < end).order_by(Task.completed_at)
    ).all()
    postponed_ids = {
        a.entity_id
        for a in db.scalars(
            select(Activity).where(
                Activity.entity_type == "task",
                Activity.created_at >= start,
                Activity.created_at < end,
                Activity.action == "postponed",
            )
        )
    }
    postponed = (
        db.scalars(select(Task).where(Task.id.in_(postponed_ids), Task.archived_at.is_(None))).all()
        if postponed_ids
        else []
    )
    now = utcnow()
    overdue = db.scalars(
        select(Task)
        .where(Task.status != "done", Task.due_at < now, Task.archived_at.is_(None))
        .order_by(Task.due_at)
        .limit(50)
    ).all()
    due_next = db.scalars(
        select(Task)
        .where(Task.status != "done", Task.due_at >= next_start, Task.due_at < next_end, Task.archived_at.is_(None))
        .order_by(Task.due_at)
    ).all()
    focus = (
        db.scalar(
            select(func.coalesce(func.sum(FocusSession.duration_seconds), 0)).where(
                FocusSession.started_at >= start, FocusSession.started_at < end
            )
        )
        or 0
    )
    events = list_events(db, start, end)
    return schemas.ReviewContext(
        review=schemas.ReviewOut.model_validate(r),
        completed=task_service.enrich(db, list(completed)),
        postponed=task_service.enrich(db, list(postponed)),
        overdue=task_service.enrich(db, list(overdue)),
        due_next=task_service.enrich(db, list(due_next)),
        focus_minutes=int(focus) // 60,
        events=[schemas.EventOut.model_validate(e) for e in events],
    )


def update_review(db: Session, kind: str, day: date, data: schemas.ReviewUpdate) -> Review:
    r = _get_or_create_review(db, kind, normalize_period(kind, day))
    changes = data.model_dump(exclude_unset=True)
    closed = changes.pop("closed", None)
    if "goals" in changes and changes["goals"] is not None:
        changes["goals"] = [g if isinstance(g, dict) else g.model_dump() for g in changes["goals"]]
    for k, v in changes.items():
        setattr(r, k, v)
    if closed is True and r.closed_at is None:
        r.closed_at = utcnow()
        log_activity(
            db,
            "review",
            r.id,
            "closed",
            f"Revisão {'semanal' if kind == 'weekly' else 'diária'} concluída ({r.period_start})",
        )
    elif closed is False:
        r.closed_at = None
    db.flush()
    return r
