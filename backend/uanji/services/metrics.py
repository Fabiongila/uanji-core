"""Indicadores do dashboard e métricas de desempenho.

Todas as métricas derivam de registos reais. "Tempo de foco" corresponde apenas a
sessões registadas pelo utilizador; não é uma medida de produtividade real.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Activity, AutomationRun, FocusSession, Notification, Project, Task, utcnow
from . import projects as project_service
from . import tasks as task_service
from .common import day_bounds, local_today, local_tz


def _count(db: Session, stmt: Any) -> int:
    return int(db.scalar(stmt) or 0)


def dashboard(db: Session) -> dict[str, Any]:
    now = utcnow()
    today = local_today(db)
    t0, t1 = day_bounds(db, today)
    week0 = t0 - timedelta(days=6)
    open_tasks = (Task.status != "done", Task.archived_at.is_(None))

    active_projects = list(
        db.scalars(
            select(Project)
            .where(Project.status.in_(["active", "blocked"]), Project.archived_at.is_(None))
            .order_by(Project.updated_at.desc())
            .limit(8)
        )
    )
    priority = db.scalars(
        select(Task)
        .where(*open_tasks, Task.parent_id.is_(None))
        .order_by(
            func.iif(Task.due_at < now, 0, 1),
            func.iif(Task.priority == "critical", 0, func.iif(Task.priority == "high", 1, 2)),
            func.iif(Task.due_at.is_(None), 1, 0),
            Task.due_at,
        )
        .limit(8)
    ).all()
    upcoming = db.scalars(
        select(Task)
        .where(*open_tasks, Task.due_at >= now, Task.due_at < now + timedelta(days=7))
        .order_by(Task.due_at)
        .limit(8)
    ).all()
    recent = db.scalars(
        select(Activity).where(Activity.sensitive.is_(False)).order_by(Activity.created_at.desc()).limit(12)
    ).all()
    focus_today = _count(
        db,
        select(func.coalesce(func.sum(FocusSession.duration_seconds), 0)).where(
            FocusSession.started_at >= t0, FocusSession.started_at < t1
        ),
    )
    focus_week = _count(
        db, select(func.coalesce(func.sum(FocusSession.duration_seconds), 0)).where(FocusSession.started_at >= week0)
    )
    running_runs = _count(
        db, select(func.count(AutomationRun.id)).where(AutomationRun.status.in_(["pending", "running"]))
    )
    failed_runs_week = _count(
        db,
        select(func.count(AutomationRun.id)).where(AutomationRun.status == "failed", AutomationRun.started_at >= week0),
    )

    alerts: list[dict[str, str]] = []
    overdue = _count(db, select(func.count(Task.id)).where(*open_tasks, Task.due_at < now))
    if overdue:
        alerts.append({"level": "warning", "title": f"{overdue} tarefa(s) atrasada(s)", "link": "/tasks?due=overdue"})
    blocked = db.scalars(select(Project).where(Project.status == "blocked")).all()
    for p in blocked[:3]:
        alerts.append(
            {
                "level": "warning",
                "title": f"Projecto bloqueado: {p.name}",
                "body": p.blocked_reason,
                "link": f"/projects/{p.id}",
            }
        )
    stale = [p for p in project_service.enrich(db, active_projects) if p.stale]
    for sp in stale[:3]:
        alerts.append(
            {
                "level": "info",
                "title": f"Sem actividade há {project_service.STALE_DAYS}+ dias: {sp.name}",
                "link": f"/projects/{sp.id}",
            }
        )
    if failed_runs_week:
        alerts.append(
            {
                "level": "error",
                "title": f"{failed_runs_week} execução(ões) de automação falhada(s) esta semana",
                "link": "/automations",
            }
        )
    unread = _count(db, select(func.count(Notification.id)).where(Notification.read_at.is_(None)))

    return {
        "generated_at": now,
        "is_empty": _count(db, select(func.count(Project.id))) == 0 and _count(db, select(func.count(Task.id))) == 0,
        "counters": {
            "active_projects": _count(db, select(func.count(Project.id)).where(Project.status == "active")),
            "blocked_projects": len(blocked),
            "pending_tasks": _count(db, select(func.count(Task.id)).where(*open_tasks)),
            "overdue_tasks": overdue,
            "done_today": _count(
                db, select(func.count(Task.id)).where(Task.completed_at >= t0, Task.completed_at < t1)
            ),
            "done_week": _count(db, select(func.count(Task.id)).where(Task.completed_at >= week0)),
            "focus_minutes_today": focus_today // 60,
            "focus_minutes_week": focus_week // 60,
            "automations_running": running_runs,
            "unread_notifications": unread,
        },
        "active_projects": project_service.enrich(db, active_projects),
        "priority_tasks": task_service.enrich(db, list(priority)),
        "upcoming": task_service.enrich(db, list(upcoming)),
        "recent_activity": recent,
        "alerts": alerts,
        "trend": completion_series(db, today - timedelta(days=13), today),
        "focus_active": task_service.active_focus(db),
    }


def _local_date(dt: datetime, db: Session) -> date:
    return dt.astimezone(local_tz(db)).date()


def completion_series(db: Session, start: date, end: date) -> list[dict[str, Any]]:
    """Série diária (dias locais) de tarefas concluídas, criadas e minutos de foco."""
    s, _ = day_bounds(db, start)
    _, e = day_bounds(db, end)
    days = {
        (start + timedelta(days=i)): {"done": 0, "created": 0, "focus_minutes": 0}
        for i in range((end - start).days + 1)
    }
    for (ts,) in db.execute(select(Task.completed_at).where(Task.completed_at >= s, Task.completed_at < e)):
        if ts is not None:
            days[_local_date(ts, db)]["done"] += 1
    for (ts,) in db.execute(select(Task.created_at).where(Task.created_at >= s, Task.created_at < e)):
        days[_local_date(ts, db)]["created"] += 1
    for ts, dur in db.execute(
        select(FocusSession.started_at, FocusSession.duration_seconds).where(
            FocusSession.started_at >= s, FocusSession.started_at < e
        )
    ):
        days[_local_date(ts, db)]["focus_minutes"] += dur // 60
    return [{"date": d.isoformat(), **v} for d, v in sorted(days.items())]


def metrics(db: Session, start: date, end: date) -> dict[str, Any]:
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        start = end - timedelta(days=366)
    s, _ = day_bounds(db, start)
    _, e = day_bounds(db, end)
    now = utcnow()

    per_project = db.execute(
        select(func.coalesce(Project.name, "Sem projecto"), func.count(Task.id))
        .select_from(Task)
        .outerjoin(Project, Project.id == Task.project_id)
        .where(Task.completed_at >= s, Task.completed_at < e)
        .group_by(Project.name)
    ).all()
    focus_per_project = db.execute(
        select(func.coalesce(Project.name, "Sem projecto"), func.sum(FocusSession.duration_seconds))
        .select_from(FocusSession)
        .outerjoin(Project, Project.id == FocusSession.project_id)
        .where(FocusSession.started_at >= s, FocusSession.started_at < e)
        .group_by(Project.name)
    ).all()
    runs = db.execute(
        select(AutomationRun.status, func.count(AutomationRun.id))
        .where(AutomationRun.started_at >= s, AutomationRun.started_at < e)
        .group_by(AutomationRun.status)
    ).all()
    series = completion_series(db, start, end)
    # Atrasos concluídos: tarefas concluídas depois do prazo, no período.
    late_done = _count(
        db,
        select(func.count(Task.id)).where(
            Task.completed_at >= s, Task.completed_at < e, Task.due_at.is_not(None), Task.completed_at > Task.due_at
        ),
    )
    projects = project_service.enrich(
        db, list(db.scalars(select(Project).where(Project.archived_at.is_(None)).order_by(Project.name)))
    )
    weekly: dict[str, int] = {}
    for p in series:
        d = date.fromisoformat(p["date"])
        key = (d - timedelta(days=d.weekday())).isoformat()
        weekly[key] = weekly.get(key, 0) + p["done"]
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": {
            "done": sum(p["done"] for p in series),
            "created": sum(p["created"] for p in series),
            "focus_minutes": sum(p["focus_minutes"] for p in series),
            "late_done": late_done,
            "overdue_now": _count(
                db,
                select(func.count(Task.id)).where(Task.status != "done", Task.archived_at.is_(None), Task.due_at < now),
            ),
        },
        "series": series,
        "weekly_done": [{"week": k, "done": v} for k, v in sorted(weekly.items())],
        "done_by_project": [{"project": n, "done": c} for n, c in per_project],
        "focus_by_project": [{"project": n, "minutes": int(m or 0) // 60} for n, m in focus_per_project],
        "automation_runs": {st: c for st, c in runs},
        "project_progress": [
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "percent": p.progress.percent if p.progress else None,
                "tasks_total": p.progress.tasks_total if p.progress else 0,
            }
            for p in projects
        ],
        "sources": {
            "done": "Tarefas com data de conclusão no período (fuso local).",
            "focus_minutes": "Soma das sessões de foco registadas manualmente ou com cronómetro. "
            "Não mede o tempo real de trabalho.",
            "project_progress": "Tarefas de topo concluídas ÷ tarefas de topo não arquivadas.",
        },
    }
