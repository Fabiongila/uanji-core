"""Centro de desempenho: mais do que contar tarefas.

Todas as medidas derivam de registos reais:
- **tempo de ciclo**: início real do trabalho (``started_at``) → conclusão;
- **tempo total (lead time)**: criação → conclusão;
- **bloqueios**: tarefas bloqueadas agora, há quanto tempo, e tempo bloqueado acumulado;
- **interrupções**: sessões de foco terminadas antes de 25 min, regressões de estado
  (em curso → por fazer/bloqueada) e, com o monitor de actividade, mudanças de aplicação;
- **objectivos**: fracção das tarefas ligadas a cada objectivo que está concluída;
- **evolução semanal**: estas medidas semana a semana.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from ..models import Activity, ActivitySession, FocusSession, Goal, Project, Task, utcnow
from .common import day_bounds, local_today, local_tz

SHORT_FOCUS_MINUTES = 25


def _hours(seconds: float) -> float:
    return round(seconds / 3600, 1)


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "avg_h": None, "median_h": None, "p85_h": None}
    vs = sorted(values)
    p85 = vs[min(len(vs) - 1, int(round(0.85 * (len(vs) - 1))))]
    return {
        "count": len(vs),
        "avg_h": _hours(sum(vs) / len(vs)),
        "median_h": _hours(statistics.median(vs)),
        "p85_h": _hours(p85),
    }


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def goal_progress(db: Session, goal: Goal) -> dict[str, Any]:
    total = db.scalar(select(func.count(Task.id)).where(Task.goal_id == goal.id, Task.archived_at.is_(None))) or 0
    done = (
        db.scalar(
            select(func.count(Task.id)).where(
                Task.goal_id == goal.id, Task.archived_at.is_(None), Task.status == "done"
            )
        )
        or 0
    )
    project = db.get(Project, goal.project_id) if goal.project_id else None
    return {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "project_id": goal.project_id,
        "project_name": project.name if project else None,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "status": goal.status,
        "tasks_total": total,
        "tasks_done": done,
        "percent": round(100 * done / total) if total else None,
    }


def center(db: Session, weeks: int = 8, project_id: str | None = None) -> dict[str, Any]:
    weeks = max(2, min(26, weeks))
    tz = local_tz(db)
    today = local_today(db)
    first_week = _week_start(today) - timedelta(weeks=weeks - 1)
    start, _ = day_bounds(db, first_week)
    now = utcnow()

    scope: list[ColumnElement[bool]] = [Task.archived_at.is_(None)]
    if project_id:
        scope.append(Task.project_id == project_id)

    done = list(db.scalars(select(Task).where(*scope, Task.completed_at >= start)))
    cycle = [(t.completed_at - t.started_at).total_seconds() for t in done if t.completed_at and t.started_at]
    lead = [(t.completed_at - t.created_at).total_seconds() for t in done if t.completed_at]

    blocked_now = list(db.scalars(select(Task).where(*scope, Task.status == "blocked")))
    blocked_now.sort(key=lambda t: t.blocked_at or now)
    blocked_items: list[dict[str, Any]] = [
        {
            "id": t.id,
            "number": t.number,
            "title": t.title,
            "reason": t.blocked_reason,
            "hours": _hours((now - t.blocked_at).total_seconds()) if t.blocked_at else None,
        }
        for t in blocked_now
    ]
    blocked_total_s = sum(t.blocked_seconds for t in done)

    # Interrupções
    focus_q = select(FocusSession).where(FocusSession.started_at >= start, FocusSession.ended_at.is_not(None))
    if project_id:
        focus_q = focus_q.where(FocusSession.project_id == project_id)
    focus = list(db.scalars(focus_q))
    short_focus = [f for f in focus if f.duration_seconds < SHORT_FOCUS_MINUTES * 60]
    regressions_q = select(Activity).where(
        Activity.entity_type == "task",
        Activity.action == "status",
        Activity.created_at >= start,
        Activity.summary.like("%in_progress → %"),
    )
    if project_id:
        regressions_q = regressions_q.where(
            Activity.entity_id.in_(select(Task.id).where(Task.project_id == project_id))
        )
    regressions = list(db.scalars(regressions_q))
    # As mudanças de aplicação medem o computador inteiro: não se dividem por projecto.
    sessions = (
        []
        if project_id
        else list(
            db.scalars(
                select(ActivitySession).where(ActivitySession.started_at >= start).order_by(ActivitySession.started_at)
            )
        )
    )
    switch_times = [b.started_at for a, b in zip(sessions, sessions[1:], strict=False) if a.app != b.app]
    active_seconds = sum(s.seconds for s in sessions)

    # Evolução semanal
    weekly: list[dict[str, Any]] = []
    for i in range(weeks):
        ws = first_week + timedelta(weeks=i)
        w0, _ = day_bounds(db, ws)
        w1, _ = day_bounds(db, ws + timedelta(days=7))
        wdone = [t for t in done if t.completed_at and w0 <= t.completed_at < w1]
        wcycle = [(t.completed_at - t.started_at).total_seconds() for t in wdone if t.completed_at and t.started_at]
        created = db.scalar(select(func.count(Task.id)).where(*scope, Task.created_at >= w0, Task.created_at < w1)) or 0
        wfocus = sum(f.duration_seconds for f in focus if w0 <= f.started_at < w1)
        wint = sum(1 for f in short_focus if w0 <= f.started_at < w1) + sum(
            1 for r in regressions if w0 <= r.created_at < w1
        )
        wswitch = sum(1 for t in switch_times if w0 <= t < w1)
        wactive = sum(s.seconds for s in sessions if w0 <= s.started_at < w1)
        weekly.append(
            {
                "week": ws.isoformat(),
                "label": ws.strftime("%d/%m"),
                "done": len(wdone),
                "created": created,
                "cycle_avg_h": _hours(sum(wcycle) / len(wcycle)) if wcycle else None,
                "blocked_h": _hours(sum(t.blocked_seconds for t in wdone)),
                "focus_h": _hours(wfocus),
                "interruptions": wint,
                "switches_per_hour": round(wswitch / (wactive / 3600), 1) if wactive >= 1800 else None,
            }
        )

    this_w, prev_w = weekly[-1], weekly[-2]
    goals = [
        goal_progress(db, g) for g in db.scalars(select(Goal).where(Goal.status == "active").order_by(Goal.target_date))
    ]
    if project_id:
        goals = [g for g in goals if g["project_id"] == project_id]

    return {
        "period": {"from": first_week.isoformat(), "to": today.isoformat(), "weeks": weeks},
        "cycle_time": _stats(cycle),
        "lead_time": _stats(lead),
        "cycle_missing": sum(1 for t in done if t.started_at is None),
        "blocked": {
            "now": len(blocked_now),
            "items": blocked_items[:10],
            "total_hours_in_done": _hours(blocked_total_s),
        },
        "interruptions": {
            "short_focus": len(short_focus),
            "focus_sessions": len(focus),
            "regressions": len(regressions),
            "per_day": round((len(short_focus) + len(regressions)) / (weeks * 7), 1),
            "app_switches_per_hour": round(len(switch_times) / (active_seconds / 3600), 1)
            if active_seconds >= 3600
            else None,
            "monitor_data": bool(sessions),
            "app_switches_scope": "project_filter" if project_id else "all",
        },
        "goals": goals,
        "weekly": weekly,
        "trend": {
            "done_delta": this_w["done"] - prev_w["done"],
            "cycle_delta_h": (
                round(this_w["cycle_avg_h"] - prev_w["cycle_avg_h"], 1)
                if this_w["cycle_avg_h"] is not None and prev_w["cycle_avg_h"] is not None
                else None
            ),
        },
        "sources": {
            "cycle_time": "Desde a primeira vez que a tarefa passou a «em curso» até à conclusão.",
            "lead_time": "Desde a criação da tarefa até à conclusão.",
            "interruptions": f"Sessões de foco com menos de {SHORT_FOCUS_MINUTES} min e tarefas que saíram de "
            "«em curso» sem ser concluídas. Mudanças de aplicação só com o monitor de actividade ligado.",
            "goals": "Tarefas concluídas ÷ tarefas ligadas ao objectivo.",
        },
        "generated_at": datetime.now(tz).isoformat(),
    }
