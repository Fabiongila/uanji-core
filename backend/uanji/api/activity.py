"""Rotas do monitor de actividade, da utilização das áreas da aplicação e da iniciativa do assistente."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..activity import insights
from ..activity import monitor as activity_monitor
from ..assistant import proactive
from ..errors import ConfirmationRequired
from ..models import ActivitySession
from ..services.common import day_bounds, get_all_settings, local_today, local_tz, put_setting
from .deps import DB

router = APIRouter()


def _screen_capture_allowed() -> bool | None:
    try:
        import Quartz  # type: ignore[import-untyped,import-not-found,unused-ignore]

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return None


@router.get("/activity/status", tags=["activity"])
def activity_status(db: DB) -> dict[str, Any]:
    m = activity_monitor.get()
    cfg = get_all_settings(db)["activity"]
    return {
        "enabled": bool(cfg.get("enabled")),
        "running": m.enabled,
        "last_error": m.last_error,
        "now": m.state.to_dict() if m.enabled else None,
        "titles_permission": _screen_capture_allowed(),
        "stored_sessions": db.query(ActivitySession).count(),
    }


@router.get("/activity/today", tags=["activity"])
def activity_today(db: DB, day: date | None = None) -> dict[str, Any]:
    s = insights.summarize(db, day)
    return {**s, "sentence": insights.summary_sentence(s)}


@router.get("/activity/patterns", tags=["activity"])
def activity_patterns(db: DB) -> dict[str, Any]:
    p = insights.patterns(db)
    return {**p, "sentence": insights.patterns_sentence(p)}


@router.get("/activity/sessions", tags=["activity"])
def activity_sessions(db: DB, day: date | None = None) -> list[dict[str, Any]]:
    start, end = day_bounds(db, day or local_today(db))
    tz = local_tz(db)
    rows = db.scalars(
        select(ActivitySession)
        .where(ActivitySession.started_at >= start, ActivitySession.started_at < end)
        .order_by(ActivitySession.started_at)
    )
    return [
        {
            "id": r.id,
            "app": r.app,
            "category": r.category,
            "context": r.context,
            "title": r.title,
            "project_id": r.project_id,
            "start": r.started_at.astimezone(tz).isoformat(),
            "end": r.ended_at.astimezone(tz).isoformat(),
            "seconds": r.seconds,
        }
        for r in rows
    ]


@router.get("/activity/git", tags=["activity"])
def activity_git(db: DB) -> list[dict[str, Any]]:
    folders = list(get_all_settings(db)["activity"].get("git_folders") or [])
    return insights.git_activity(folders) if folders else []


@router.delete("/activity", tags=["activity"])
def delete_activity(confirm: bool = False) -> dict[str, int]:
    if not confirm:
        raise ConfirmationRequired("Apagar todo o registo de actividade no computador? Confirme a operação.")
    return {"deleted": activity_monitor.ActivityMonitor.purge(0)}


# --------------------------------------------------------------------------- Utilização (modo adaptativo)


class UsageIn(BaseModel):
    area: str = Field(min_length=1, max_length=40, pattern=r"^[a-z-]+$")


@router.post("/usage", tags=["activity"])
def record_usage(db: DB, body: UsageIn) -> dict[str, float]:
    """Conta visitas às áreas da aplicação, com decaimento (o uso recente pesa mais)."""
    usage: dict[str, float] = dict(get_all_settings(db).get("usage") or {})
    usage = {k: round(v * 0.97, 3) for k, v in usage.items() if v * 0.97 >= 0.05}
    usage[body.area] = round(usage.get(body.area, 0.0) + 1.0, 3)
    put_setting(db, "usage", usage)
    return usage


# --------------------------------------------------------------------------- Iniciativa


@router.post("/proactive/check", tags=["assistant"])
def proactive_check() -> dict[str, Any]:
    """Avalia agora as regras de iniciativa (útil para testar). Devolve a mensagem entregue, se houver."""
    engine = proactive.get()
    if engine is None:
        return {"delivered": None, "running": False}
    n = engine.tick()
    return {"delivered": n.to_dict() if n else None, "running": True}
