"""Relatórios do assistente, construídos apenas com dados registados na aplicação.

Cada relatório separa explicitamente:
- ``facts``: factos registados (contagens e registos existentes);
- ``derived``: cálculos feitos a partir desses registos;
- ``recommendations``: sugestões (claramente marcadas como tal);
- ``unavailable``: o que a aplicação não sabe ou não mede.

O texto falado (``speech``) é gerado a partir das mesmas secções, sem acrescentar nada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Automation, AutomationRun, Event, FocusSession, Note, Project, Task
from ..services import metrics
from ..services import projects as project_service
from ..services import tasks as task_service
from ..services.common import day_bounds, local_today

ReportKind = Literal["daily", "weekly", "projects", "next_steps", "automations", "problems"]
SectionKind = Literal["facts", "derived", "recommendations", "unavailable"]

SECTION_TITLE: dict[str, str] = {
    "facts": "Factos registados",
    "derived": "Cálculos a partir dos dados",
    "recommendations": "Recomendações",
    "unavailable": "Informação indisponível",
}
RUN_STATUS_LABEL = {
    "success": "concluídas",
    "failed": "falhadas",
    "running": "em curso",
    "pending": "pendentes",
    "cancelled": "canceladas",
    "skipped": "ignoradas",
}
TITLES: dict[str, str] = {
    "daily": "Relatório do dia",
    "weekly": "Relatório semanal de produtividade",
    "projects": "Estado dos projectos",
    "next_steps": "Próximos passos",
    "automations": "Automações de hoje",
    "problems": "Principais problemas",
}


@dataclass
class Section:
    kind: SectionKind
    items: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return SECTION_TITLE[self.kind]


@dataclass
class Report:
    kind: str
    title: str
    sections: list[Section]
    speech: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "sections": [{**asdict(s), "title": s.title} for s in self.sections if s.items],
            "speech": self.speech,
        }

    def section(self, kind: SectionKind) -> Section:
        for s in self.sections:
            if s.kind == kind:
                return s
        s = Section(kind)
        self.sections.append(s)
        return s


def _n(db: Session, stmt: Any) -> int:
    return int(db.scalar(stmt) or 0)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _titles(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(f"«{t}»" for t in items[:limit])
    return shown + (f" e mais {len(items) - limit}" if len(items) > limit else "")


def _speech(r: Report, max_items: int = 4) -> str:
    """Leitura em voz alta: título + até ``max_items`` itens por secção, por ordem."""
    parts = [f"{r.title}."]
    for s in r.sections:
        if not s.items:
            continue
        items = s.items[:max_items]
        rest = len(s.items) - len(items)
        text = " ".join(i if i.endswith(".") else i + "." for i in items)
        if rest > 0:
            text += f" Há mais {rest} ponto(s) no relatório escrito."
        parts.append(f"{s.title}: {text}")
    return " ".join(parts)


# --------------------------------------------------------------------------- Construtores


def _next_steps(db: Session, r: Report, limit: int = 3) -> None:
    d = metrics.dashboard(db)
    tasks = d["priority_tasks"][:limit]
    rec = r.section("recommendations")
    for t in tasks:
        why = (
            "atrasada"
            if t.overdue
            else {"high": "prioridade alta", "critical": "prioridade crítica"}.get(t.priority, "")
        )
        rec.items.append(f"Tratar «{t.title}»" + (f" ({why})" if why else ""))
    if not tasks:
        rec.items.append("Não há tarefas em aberto. Pode planear a próxima etapa de um projecto activo.")


def daily(db: Session) -> Report:
    r = Report(
        "daily",
        TITLES["daily"],
        [Section("facts"), Section("derived"), Section("recommendations"), Section("unavailable")],
    )
    today = local_today(db)
    t0, t1 = day_bounds(db, today)
    done = list(db.scalars(select(Task.title).where(Task.completed_at >= t0, Task.completed_at < t1)))
    created = _n(db, select(func.count(Task.id)).where(Task.created_at >= t0, Task.created_at < t1))
    notes = _n(db, select(func.count(Note.id)).where(Note.created_at >= t0, Note.created_at < t1))
    focus = _n(
        db,
        select(func.coalesce(func.sum(FocusSession.duration_seconds), 0)).where(
            FocusSession.started_at >= t0, FocusSession.started_at < t1
        ),
    )
    events = list(db.scalars(select(Event.title).where(Event.start_at >= t0, Event.start_at < t1)))
    runs = dict(
        db.execute(
            select(AutomationRun.status, func.count(AutomationRun.id))
            .where(AutomationRun.started_at >= t0, AutomationRun.started_at < t1)
            .group_by(AutomationRun.status)
        ).all()
    )
    f = r.section("facts")
    f.items.append(f"Concluiu {_plural(len(done), 'tarefa', 'tarefas')} hoje" + (f": {_titles(done)}" if done else ""))
    f.items.append(f"Criou {_plural(created, 'tarefa', 'tarefas')} e {_plural(notes, 'nota', 'notas')}")
    if focus:
        f.items.append(f"Registou {focus // 60} minutos de foco")
    if events:
        f.items.append(f"{_plural(len(events), 'compromisso', 'compromissos')} na agenda: {_titles(events, 4)}")
    if runs:
        f.items.append("Automações: " + ", ".join(f"{v} {RUN_STATUS_LABEL.get(k, k)}" for k, v in runs.items()))
    now_overdue = _n(
        db,
        select(func.count(Task.id)).where(
            Task.status != "done", Task.archived_at.is_(None), Task.due_at < t1, Task.due_at.is_not(None)
        ),
    )
    due_today_open = _n(
        db,
        select(func.count(Task.id)).where(
            Task.status != "done", Task.archived_at.is_(None), Task.due_at >= t0, Task.due_at < t1
        ),
    )
    d = r.section("derived")
    if due_today_open:
        d.items.append(f"Ficam {_plural(due_today_open, 'tarefa', 'tarefas')} com prazo hoje por concluir")
    if now_overdue:
        d.items.append(f"{_plural(now_overdue, 'tarefa está', 'tarefas estão')} atrasadas ou vencem hoje")
    _next_steps(db, r)
    u = r.section("unavailable")
    if not focus:
        u.items.append("Não há sessões de foco registadas hoje; a aplicação não mede o tempo de trabalho real")
    from ..activity import insights

    act = insights.summarize(db, today)
    if act["has_data"]:
        f.items.append(insights.summary_sentence(act).rstrip("."))
        if act["switches"] >= 40:
            d.items.append(f"Mudou de aplicação {act['switches']} vezes hoje; blocos de foco podem ajudar")
    elif act["monitor_enabled"]:
        u.items.append("Ainda não há actividade registada no computador hoje")
    else:
        u.items.append(
            "Trabalho feito no computador fora da aplicação não é conhecido (monitor de actividade desligado)"
        )
    r.speech = _speech(r)
    return r


def weekly(db: Session) -> Report:
    r = Report(
        "weekly",
        TITLES["weekly"],
        [Section("facts"), Section("derived"), Section("recommendations"), Section("unavailable")],
    )
    today = local_today(db)
    start = today - timedelta(days=6)
    m = metrics.metrics(db, start, today)
    prev = metrics.metrics(db, start - timedelta(days=7), start - timedelta(days=1))
    t, pt = m["totals"], prev["totals"]
    f = r.section("facts")
    f.items.append(f"Nos últimos 7 dias concluiu {_plural(t['done'], 'tarefa', 'tarefas')} e criou {t['created']}")
    if t["focus_minutes"]:
        f.items.append(f"Registou {t['focus_minutes']} minutos de foco")
    if t["late_done"]:
        f.items.append(f"{_plural(t['late_done'], 'tarefa foi concluída', 'tarefas foram concluídas')} depois do prazo")
    by_project = sorted(m["done_by_project"], key=lambda x: -x["done"])
    if by_project:
        f.items.append("Concluídas por projecto: " + ", ".join(f"{p['project']} ({p['done']})" for p in by_project[:4]))
    runs = m["automation_runs"]
    if runs:
        f.items.append("Automações: " + ", ".join(f"{v} {RUN_STATUS_LABEL.get(k, k)}" for k, v in runs.items()))
    d = r.section("derived")
    diff = t["done"] - pt["done"]
    if pt["done"] or t["done"]:
        trend = "mais" if diff > 0 else "menos"
        d.items.append(
            "O mesmo número de tarefas concluídas que na semana anterior"
            if diff == 0
            else f"{abs(diff)} tarefa(s) concluída(s) a {trend} do que na semana anterior ({pt['done']})"
        )
    if t["created"] > t["done"]:
        d.items.append(f"Entraram mais tarefas ({t['created']}) do que as concluídas ({t['done']}): o backlog cresceu")
    if t["overdue_now"]:
        d.items.append(f"{_plural(t['overdue_now'], 'tarefa está', 'tarefas estão')} atrasadas neste momento")
    stalled = [p for p in m["project_progress"] if p["status"] == "active" and p["tasks_total"] == 0]
    if stalled:
        d.items.append(f"Projectos activos sem tarefas: {_titles([p['name'] for p in stalled], 3)}")
    _next_steps(db, r)
    if t["overdue_now"] > 3:
        r.section("recommendations").items.append("Rever prazos das tarefas atrasadas na revisão semanal")
    r.section("unavailable").items.append("O tempo de foco só inclui sessões registadas; não mede produtividade real")
    r.speech = _speech(r)
    return r


def project_delays(db: Session) -> list[dict[str, Any]]:
    """Atraso por projecto activo: dias após a data de fim e tarefas atrasadas (cálculo derivado)."""
    today = local_today(db)
    projects = project_service.enrich(
        db,
        list(
            db.scalars(
                select(Project).where(
                    Project.archived_at.is_(None), Project.status.in_(["active", "blocked", "paused"])
                )
            )
        ),
    )
    out: list[dict[str, Any]] = []
    for p in projects:
        days_late = (today - p.due_date).days if p.due_date and p.due_date < today else 0
        overdue = p.progress.overdue_tasks if p.progress else 0
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "days_late": days_late,
                "overdue_tasks": overdue,
                "percent": p.progress.percent if p.progress else None,
            }
        )
    out.sort(key=lambda x: (-x["days_late"], -x["overdue_tasks"]))
    return out


def projects(db: Session) -> Report:
    r = Report(
        "projects",
        TITLES["projects"],
        [Section("facts"), Section("derived"), Section("recommendations"), Section("unavailable")],
    )
    delays = project_delays(db)
    f = r.section("facts")
    if not delays:
        f.items.append("Não há projectos activos, bloqueados ou em pausa")
    for p in delays[:8]:
        status = {"active": "activo", "blocked": "bloqueado", "paused": "em pausa"}[p["status"]]
        prog = f"{p['percent']}% concluído" if p["percent"] is not None else "sem tarefas"
        f.items.append(f"{p['name']}: {status}, {prog}")
    d = r.section("derived")
    late = [p for p in delays if p["days_late"] or p["overdue_tasks"]]
    if late:
        w = late[0]
        why = []
        if w["days_late"]:
            why.append(f"{w['days_late']} dia(s) depois da data de fim")
        if w["overdue_tasks"]:
            why.append(_plural(w["overdue_tasks"], "tarefa atrasada", "tarefas atrasadas"))
        d.items.append(f"O projecto mais atrasado é {w['name']}: {', '.join(why)}")
    elif delays:
        d.items.append("Nenhum projecto tem a data de fim ultrapassada nem tarefas atrasadas")
    blocked = [p["name"] for p in delays if p["status"] == "blocked"]
    if blocked:
        r.section("recommendations").items.append(f"Resolver o bloqueio de {_titles(blocked, 3)}")
    if late:
        r.section("recommendations").items.append(f"Rever prazos e tarefas atrasadas de {late[0]['name']}")
    no_due = [p["name"] for p in delays if p["days_late"] == 0]
    if delays and len(no_due) == len(delays):
        r.section("unavailable").items.append(
            "Sem data de fim definida, o atraso de um projecto só é medido pelas tarefas atrasadas"
        )
    r.speech = _speech(r)
    return r


def next_steps(db: Session) -> Report:
    r = Report("next_steps", TITLES["next_steps"], [Section("facts"), Section("recommendations")])
    d = metrics.dashboard(db)
    c = d["counters"]
    r.section("facts").items.append(
        f"{_plural(c['pending_tasks'], 'tarefa pendente', 'tarefas pendentes')}, "
        f"{_plural(c['overdue_tasks'], 'atrasada', 'atrasadas')}"
    )
    _next_steps(db, r, limit=4)
    r.speech = _speech(r)
    return r


def automations(db: Session) -> Report:
    r = Report("automations", TITLES["automations"], [Section("facts"), Section("derived"), Section("unavailable")])
    today = local_today(db)
    t0, t1 = day_bounds(db, today)
    rows = db.execute(
        select(AutomationRun.status, AutomationRun.error, Automation.name)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .where(AutomationRun.started_at >= t0, AutomationRun.started_at < t1)
        .order_by(AutomationRun.started_at)
    ).all()
    f = r.section("facts")
    if not rows:
        f.items.append("Nenhuma automação foi executada hoje")
    for status, error, name in rows[:10]:
        f.items.append(
            f"{name}: {RUN_STATUS_LABEL.get(status, status).rstrip('s')}" + (f" ({error[:120]})" if error else "")
        )
    failed = sum(1 for s, _, _ in rows if s == "failed")
    if rows:
        r.section("derived").items.append(f"{failed} de {len(rows)} execução(ões) falharam hoje")
    active = _n(db, select(func.count(Automation.id)).where(Automation.enabled.is_(True)))
    f.items.append(f"{_plural(active, 'automação activa', 'automações activas')}")
    r.speech = _speech(r)
    return r


def problems(db: Session) -> Report:
    r = Report("problems", TITLES["problems"], [Section("facts"), Section("recommendations")])
    d = metrics.dashboard(db)
    f = r.section("facts")
    for a in d["alerts"]:
        f.items.append(a["title"] + (f": {a['body']}" if a.get("body") else ""))
    blocked_tasks = task_service.list_tasks(db, status=["blocked"], limit=5).items
    for t in blocked_tasks:
        f.items.append(f"Tarefa bloqueada «{t.title}»" + (f": {t.blocked_reason}" if t.blocked_reason else ""))
    if not f.items:
        f.items.append("Não há atrasos, bloqueios, projectos parados nem automações falhadas registados")
    _next_steps(db, r, limit=2)
    r.speech = _speech(r)
    return r


BUILDERS = {
    "daily": daily,
    "weekly": weekly,
    "projects": projects,
    "next_steps": next_steps,
    "automations": automations,
    "problems": problems,
}


def build(db: Session, kind: str) -> Report:
    return BUILDERS[kind](db)
