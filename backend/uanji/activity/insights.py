"""Resumos e padrões calculados a partir das sessões de actividade registadas.

Todos os valores são derivados de registos reais. Sem monitor activo não há dados e os
resumos dizem-no, em vez de estimar.
"""

from __future__ import annotations

import shutil
import subprocess  # noqa: S404 (comandos git fixos, sem shell)
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ActivitySession, Project, Task
from ..services.common import day_bounds, get_all_settings, local_today, local_tz
from .monitor import CATEGORY_LABEL


def fmt_duration(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"


def _sessions(db: Session, start: datetime, end: datetime) -> list[ActivitySession]:
    return list(
        db.scalars(
            select(ActivitySession)
            .where(ActivitySession.started_at >= start, ActivitySession.started_at < end)
            .order_by(ActivitySession.started_at)
        )
    )


def summarize(db: Session, day: date | None = None) -> dict[str, Any]:
    day = day or local_today(db)
    start, end = day_bounds(db, day)
    rows = _sessions(db, start, end)
    tz = local_tz(db)
    enabled = bool(get_all_settings(db)["activity"].get("enabled"))
    total = sum(r.seconds for r in rows)
    by_app: Counter[str] = Counter()
    by_cat: Counter[str] = Counter()
    by_project: Counter[str] = Counter()
    by_context: Counter[str] = Counter()
    hours = [0] * 24
    for r in rows:
        by_app[r.app] += r.seconds
        by_cat[r.category] += r.seconds
        if r.project_id:
            by_project[r.project_id] += r.seconds
        if r.context:
            by_context[r.context] += r.seconds
        hours[r.started_at.astimezone(tz).hour] += r.seconds
    names = {p.id: p.name for p in db.scalars(select(Project).where(Project.id.in_(list(by_project))))}
    switches = sum(1 for a, b in zip(rows, rows[1:], strict=False) if a.app != b.app)
    longest = max(rows, key=lambda r: r.seconds, default=None)
    return {
        "date": day.isoformat(),
        "monitor_enabled": enabled,
        "has_data": bool(rows),
        "active_seconds": total,
        "first_at": rows[0].started_at.astimezone(tz).strftime("%H:%M") if rows else None,
        "last_at": rows[-1].ended_at.astimezone(tz).strftime("%H:%M") if rows else None,
        "apps": [{"app": a, "seconds": s} for a, s in by_app.most_common(8)],
        "categories": [
            {"category": c, "label": CATEGORY_LABEL.get(c, c), "seconds": s} for c, s in by_cat.most_common()
        ],
        "projects": [{"id": pid, "name": names.get(pid, "?"), "seconds": s} for pid, s in by_project.most_common(5)],
        "contexts": [{"context": c, "seconds": s} for c, s in by_context.most_common(5)],
        "hours": hours,
        "switches": switches,
        "longest": {"app": longest.app, "context": longest.context, "seconds": longest.seconds} if longest else None,
    }


def summary_sentence(s: dict[str, Any]) -> str:
    if not s["monitor_enabled"] and not s["has_data"]:
        return "O monitor de actividade está desligado, por isso não sei o que fez no computador hoje."
    if not s["has_data"]:
        return "Ainda não há actividade registada no computador hoje."
    parts = [f"Hoje esteve activo no computador {fmt_duration(s['active_seconds'])}, desde as {s['first_at']}"]
    apps = s["apps"][:3]
    if apps:
        parts.append("mais tempo em " + ", ".join(f"{a['app']} ({fmt_duration(a['seconds'])})" for a in apps))
    text = "; ".join(parts) + "."
    if s["projects"]:
        p = s["projects"][0]
        text += f" O projecto com mais tempo foi {p['name']} ({fmt_duration(p['seconds'])})."
    elif s["contexts"]:
        c = s["contexts"][0]
        text += f" No editor, trabalhou sobretudo em «{c['context']}» ({fmt_duration(c['seconds'])})."
    return text


def patterns(db: Session, days: int = 14) -> dict[str, Any]:
    """Padrões dos últimos ``days`` dias (excluindo hoje): hora de início, horas activas, apps."""
    today = local_today(db)
    tz = local_tz(db)
    start, _ = day_bounds(db, today - timedelta(days=days))
    end, _ = day_bounds(db, today)
    rows = _sessions(db, start, end)
    per_day: dict[date, list[ActivitySession]] = defaultdict(list)
    for r in rows:
        per_day[r.started_at.astimezone(tz).date()].append(r)
    starts = [min(rs, key=lambda r: r.started_at).started_at.astimezone(tz) for rs in per_day.values()]
    hours = [0] * 24
    apps: Counter[str] = Counter()
    for r in rows:
        hours[r.started_at.astimezone(tz).hour] += r.seconds
        apps[r.app] += r.seconds
    done_hours = [0] * 24
    for (ts,) in db.execute(select(Task.completed_at).where(Task.completed_at >= start, Task.completed_at < end)):
        if ts:
            done_hours[ts.astimezone(tz).hour] += 1
    peak = sorted(range(24), key=lambda h: -hours[h])[:3]
    avg_start = None
    if starts:
        mins = sum(s.hour * 60 + s.minute for s in starts) / len(starts)
        avg_start = f"{int(mins // 60):02d}:{int(mins % 60):02d}"
    return {
        "days_with_data": len(per_day),
        "avg_start": avg_start,
        "avg_active_seconds": int(sum(r.seconds for r in rows) / len(per_day)) if per_day else 0,
        "peak_hours": sorted(h for h in peak if hours[h] > 0),
        "top_apps": [{"app": a, "seconds": s} for a, s in apps.most_common(5)],
        "hours": hours,
        "tasks_done_by_hour": done_hours,
    }


def patterns_sentence(p: dict[str, Any]) -> str:
    if p["days_with_data"] < 3:
        return "Ainda tenho poucos dias de actividade registada para identificar padrões (são precisos pelo menos 3)."
    parts = [
        f"Nos últimos {p['days_with_data']} dias com registo, começou em média às {p['avg_start']}",
        f"esteve activo cerca de {fmt_duration(p['avg_active_seconds'])} por dia",
    ]
    if p["peak_hours"]:
        parts.append("as horas mais intensas foram " + ", ".join(f"{h}h" for h in p["peak_hours"]))
    if p["top_apps"]:
        parts.append("a aplicação mais usada foi " + p["top_apps"][0]["app"])
    return "; ".join(parts) + "."


# --------------------------------------------------------------------------- Git

_git_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_git_lock = threading.Lock()


def git_activity(folders: list[str], since: str = "midnight", max_repos: int = 40) -> list[dict[str, Any]]:
    """Commits do utilizador (autor = user.email do git) desde ``since`` nos repositórios das pastas indicadas.

    Considera cada pasta e as suas subpastas directas. Resultado em cache durante 5 minutos.
    """
    git = shutil.which("git")
    if not git:
        return []
    key = f"{since}|{'|'.join(folders)}"
    with _git_lock:
        hit = _git_cache.get(key)
        if hit and time.monotonic() - hit[0] < 300:
            return hit[1]
    repos: list[Path] = []
    for f in folders:
        base = Path(f).expanduser()
        if not base.is_dir():
            continue
        cands = [base, *sorted(p for p in base.iterdir() if p.is_dir())]
        repos += [p for p in cands if (p / ".git").exists()]
    out = []
    for repo in repos[:max_repos]:
        try:
            email = subprocess.run(  # noqa: S603
                [git, "-C", str(repo), "config", "user.email"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            args = [git, "-C", str(repo), "log", f"--since={since}", "--pretty=%h%x09%s", "--no-merges"]
            if email:
                args.append(f"--author={email}")
            log_out = subprocess.run(args, capture_output=True, text=True, timeout=5).stdout  # noqa: S603
        except (subprocess.SubprocessError, OSError):
            continue
        commits = [line.split("\t", 1) for line in log_out.splitlines() if "\t" in line]
        if commits:
            out.append(
                {"repo": repo.name, "path": str(repo), "commits": [{"hash": h, "message": m} for h, m in commits]}
            )
    with _git_lock:
        _git_cache[key] = (time.monotonic(), out)
    return out
