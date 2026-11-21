"""Notificações internas e geração de lembretes.

As notificações internas vivem na base de dados. As nativas do macOS são enviadas
pela camada desktop (plugin de notificações do Tauri), que consulta ``/notifications/native``
e marca cada uma como enviada; o backend nunca as mostra directamente.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Notification, Review, Task, utcnow
from .common import get_all_settings, local_today, local_tz

CATEGORIES = ("deadline", "overdue", "review", "automation", "backup", "system")
RETENTION_DAYS = 90


def _prefs(db: Session) -> dict[str, Any]:
    prefs = get_all_settings(db)["notifications"]
    assert isinstance(prefs, dict)
    return prefs


def create(
    db: Session,
    *,
    category: str,
    title: str,
    body: str = "",
    level: str = "info",
    link: str = "",
    dedupe_key: str | None = None,
    respect_preferences: bool = True,
) -> Notification | None:
    """Cria uma notificação; devolve ``None`` se desactivada ou duplicada."""
    prefs = _prefs(db)
    if respect_preferences and (not prefs.get("enabled", True) or not prefs["categories"].get(category, True)):
        return None
    if dedupe_key and db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    n = Notification(category=category, title=title[:300], body=body, level=level, link=link, dedupe_key=dedupe_key)
    try:
        with db.begin_nested():
            db.add(n)
    except IntegrityError:
        return None
    return n


def list_notifications(db: Session, unread_only: bool = False, limit: int = 50) -> list[Notification]:
    stmt = select(Notification)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return list(db.scalars(stmt.order_by(Notification.created_at.desc()).limit(limit)))


def unread_count(db: Session) -> int:
    return int(db.scalar(select(func.count(Notification.id)).where(Notification.read_at.is_(None))) or 0)


def mark_read(db: Session, ids: list[str] | None) -> int:
    stmt = update(Notification).where(Notification.read_at.is_(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    return db.execute(stmt.values(read_at=utcnow())).rowcount  # type: ignore[attr-defined, no-any-return]


def _in_quiet_hours(db: Session, prefs: dict[str, Any]) -> bool:
    now = datetime.now(local_tz(db)).time()
    try:
        qs = time.fromisoformat(prefs.get("quiet_start", "22:00"))
        qe = time.fromisoformat(prefs.get("quiet_end", "07:00"))
    except ValueError:
        return False
    return (qs <= now or now < qe) if qs > qe else (qs <= now < qe)


def pending_native(db: Session) -> list[Notification]:
    """Notificações a mostrar nativamente (respeita a preferência e o horário de silêncio)."""
    prefs = _prefs(db)
    if not prefs.get("native") or _in_quiet_hours(db, prefs):
        return []
    since = utcnow() - timedelta(hours=1)
    return list(
        db.scalars(
            select(Notification)
            .where(
                Notification.native_sent.is_(False), Notification.read_at.is_(None), Notification.created_at >= since
            )
            .limit(5)
        )
    )


def mark_native_sent(db: Session, ids: list[str]) -> None:
    db.execute(update(Notification).where(Notification.id.in_(ids)).values(native_sent=True))


def generate_reminders(db: Session) -> int:
    """Gera lembretes de prazos, atrasos e revisões. Idempotente (chaves de deduplicação)."""
    prefs = _prefs(db)
    created = 0
    now = utcnow()
    horizon = now + timedelta(hours=int(prefs.get("deadline_hours", 24)))
    for t in db.scalars(
        select(Task).where(
            Task.status != "done", Task.archived_at.is_(None), Task.due_at >= now, Task.due_at <= horizon
        )
    ):
        assert t.due_at is not None
        local = t.due_at.astimezone(local_tz(db)).strftime("%d/%m %H:%M")
        if create(
            db,
            category="deadline",
            level="warning",
            title=f"Prazo próximo: {t.title}",
            body=f"Prazo: {local}",
            link=f"/tasks/{t.id}",
            dedupe_key=f"deadline:{t.id}:{t.due_at.isoformat()}",
        ):
            created += 1
    for t in db.scalars(select(Task).where(Task.status != "done", Task.archived_at.is_(None), Task.due_at < now)):
        assert t.due_at is not None
        if create(
            db,
            category="overdue",
            level="error",
            title=f"Tarefa atrasada: {t.title}",
            link=f"/tasks/{t.id}",
            dedupe_key=f"overdue:{t.id}:{t.due_at.isoformat()}",
        ):
            created += 1

    tz = local_tz(db)
    local_now = datetime.now(tz)
    today = local_today(db)
    try:
        review_time = time.fromisoformat(prefs.get("daily_review_time", "18:00"))
    except ValueError:
        review_time = time(18, 0)
    if local_now.time() >= review_time:
        closed = db.scalar(select(Review.closed_at).where(Review.kind == "daily", Review.period_start == today))
        if closed is None and create(
            db,
            category="review",
            title="Revisão diária pendente",
            body="Reveja o dia e planeie o seguinte.",
            link="/review",
            dedupe_key=f"review:daily:{today.isoformat()}",
        ):
            created += 1
        if today.weekday() == int(prefs.get("weekly_review_day", 4)):
            week = today - timedelta(days=today.weekday())
            wclosed = db.scalar(select(Review.closed_at).where(Review.kind == "weekly", Review.period_start == week))
            if wclosed is None and create(
                db,
                category="review",
                title="Revisão semanal pendente",
                link="/planning",
                dedupe_key=f"review:weekly:{week.isoformat()}",
            ):
                created += 1
    db.execute(
        delete(Notification).where(
            Notification.created_at < now - timedelta(days=RETENTION_DAYS), Notification.read_at.is_not(None)
        )
    )
    return created
