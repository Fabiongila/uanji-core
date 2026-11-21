"""Ferramentas internas do assistente: a única forma de o assistente ler ou alterar dados.

Cada ferramenta tem nome, descrição, parâmetros tipados (Pydantic), nível de risco e
chama apenas os serviços da aplicação. Não há SQL arbitrário, código gerado nem
comandos de terminal.

Níveis de risco:
- ``read``: consulta; executa directamente.
- ``create``: acrescenta dados (reversível); confirmação conforme as Definições.
- ``update``: altera dados existentes ou executa automações; confirmação conforme as Definições.
- ``destructive``: elimina ou arquiva; exige SEMPRE confirmação explícita.
"""

from __future__ import annotations

import difflib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..errors import NotFound, ValidationFailed
from ..models import Automation, AutomationRun, Checklist, Note, Project, Task, TaskDependency, utcnow
from ..services import agenda as agenda_service
from ..services import checklists as checklist_service
from ..services import metrics
from ..services import notes as note_service
from ..services import projects as project_service
from ..services import tasks as task_service
from ..services.commands import ROUTES
from ..services.common import day_bounds, get_all_settings, local_today, local_tz, search
from . import reports

Risk = Literal["read", "system", "create", "update", "destructive"]

RISK_LABEL = {
    "read": "consulta",
    "system": "acção no sistema",
    "create": "cria dados",
    "update": "altera dados",
    "destructive": "irreversível ou destrutiva",
}
STATUS_LABEL = {"todo": "por fazer", "in_progress": "em curso", "blocked": "bloqueada", "done": "concluída"}
PROJECT_STATUS_LABEL = {
    "planned": "planeado",
    "active": "activo",
    "paused": "em pausa",
    "blocked": "bloqueado",
    "done": "concluído",
    "archived": "arquivado",
}
PRIORITY_LABEL = {"low": "baixa", "medium": "média", "high": "alta", "critical": "crítica"}


class Ambiguous(ValidationFailed):
    """Mais do que um registo corresponde à referência dada."""

    def __init__(self, message: str, options: list[dict[str, str]]) -> None:
        super().__init__(message, {"options": options})
        self.options = options


@dataclass
class ToolResult:
    message: str
    data: Any = None
    entity: dict[str, str] | None = None  # {"type", "id", "label"} — usado como contexto da conversa
    navigate: str | None = None
    report: reports.Report | None = None
    # Outra ferramenta que deve tratar o pedido (ex.: «abre o Chrome» → abrir aplicação).
    delegate: tuple[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    risk: Risk
    run: Callable[[Session, Any], ToolResult]
    describe: Callable[[Session, Any], list[str]] | None = None  # detalhes mostrados antes da confirmação
    summary: Callable[[Session, Any], str] = field(default=lambda db, p: "")


# --------------------------------------------------------------------------- Resolução de referências


def norm(s: str) -> str:
    return " ".join(
        "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").split()
    )


def _pick[T](items: list[T], label: Callable[[T], str], ref: str, kind: str) -> T:
    r = norm(ref)
    exact = [i for i in items if norm(label(i)) == r]
    if len(exact) == 1:
        return exact[0]
    contains = [i for i in items if r and r in norm(label(i))]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        raise Ambiguous(
            f"Há {len(contains)} {kind}s que correspondem a «{ref}».",
            [{"id": getattr(i, "id", ""), "label": label(i)} for i in contains[:6]],
        )
    names = [norm(label(i)) for i in items]
    close = difflib.get_close_matches(r, names, n=3, cutoff=0.72)
    if len(close) == 1:
        return items[names.index(close[0])]
    if close:
        found = [items[names.index(c)] for c in close]
        raise Ambiguous(
            f"Não tenho a certeza de qual {kind} se refere.",
            [{"id": getattr(i, "id", ""), "label": label(i)} for i in found],
        )
    raise NotFound(f"Não encontrei nenhum {kind} correspondente a «{ref}».")


def resolve_project(db: Session, ref: str, include_archived: bool = False) -> Project:
    p = db.get(Project, ref)
    if p is not None:
        return p
    stmt = select(Project)
    if not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))
    return _pick(list(db.scalars(stmt)), lambda x: x.name, ref, "projecto")


def resolve_task(db: Session, ref: str, open_only: bool = True) -> Task:
    t = db.get(Task, ref)
    if t is not None:
        return t
    stmt = select(Task).where(Task.archived_at.is_(None))
    if open_only:
        stmt = stmt.where(Task.status != "done")
    return _pick(list(db.scalars(stmt)), lambda x: x.title, ref, "tarefa")


def resolve_automation(db: Session, ref: str) -> Automation:
    a = db.get(Automation, ref)
    if a is not None:
        return a
    return _pick(list(db.scalars(select(Automation))), lambda x: x.name, ref, "automação")


def parse_due(db: Session, value: str | None) -> datetime | None:
    """«hoje», «amanhã», «+3d», «25/10», «2026-10-25» → fim do dia (18:00 local)."""
    if not value:
        return None
    today = local_today(db)
    v = norm(value)
    weekdays = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    d: date | None = None
    if v == "hoje":
        d = today
    elif v == "amanha":
        d = today + timedelta(days=1)
    elif v.startswith("+") and v[1:].rstrip("d").isdigit():
        d = today + timedelta(days=int(v[1:].rstrip("d")))
    elif any(v.startswith(w) for w in weekdays):
        target = next(i for i, w in enumerate(weekdays) if v.startswith(w))
        d = today + timedelta(days=(target - today.weekday()) % 7 or 7)
    else:
        for fmt in ("%d/%m", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(value.strip(), fmt).date()
                d = parsed.replace(year=today.year) if fmt == "%d/%m" else parsed
                break
            except ValueError:
                continue
    if d is None:
        raise ValidationFailed(f"Data não reconhecida: «{value}». Use hoje, amanhã, um dia da semana ou dd/mm.")
    return datetime.combine(d, time(18, 0), tzinfo=local_tz(db))


def _fmt_due(db: Session, dt: datetime | None) -> str:
    if dt is None:
        return "sem prazo"
    local = dt.astimezone(local_tz(db)).date()
    delta = (local - local_today(db)).days
    if delta == 0:
        return "hoje"
    if delta == 1:
        return "amanhã"
    if delta == -1:
        return "ontem"
    if delta < 0:
        return f"há {-delta} dias"
    return f"{local.strftime('%d/%m')}"


def brief_task(db: Session, t: schemas.TaskOut) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "due": _fmt_due(db, t.due_at),
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "overdue": t.overdue,
        "project": t.project_name,
    }


def _task_line(db: Session, t: schemas.TaskOut) -> str:
    bits = [f"«{t.title}»"]
    if t.overdue:
        bits.append(f"atrasada (prazo {_fmt_due(db, t.due_at)})")
    elif t.due_at:
        bits.append(f"prazo {_fmt_due(db, t.due_at)}")
    if t.priority in ("high", "critical"):
        bits.append(f"prioridade {PRIORITY_LABEL[t.priority]}")
    if t.project_name:
        bits.append(f"projecto {t.project_name}")
    return ", ".join(bits)


# --------------------------------------------------------------------------- Parâmetros


class EmptyIn(BaseModel):
    pass


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class ProjectRefIn(BaseModel):
    project: str = Field(min_length=1, max_length=200, description="Id ou nome (parcial) do projecto.")


class ListTasksIn(BaseModel):
    project: str | None = Field(default=None, description="Id ou nome do projecto.")
    status: list[schemas.TaskStatus] | None = None
    due: Literal["overdue", "today", "week"] | None = None
    limit: int = Field(default=15, ge=1, le=50)


class NoteRefIn(BaseModel):
    note_id: str


class AgendaIn(BaseModel):
    day: str = Field(default="hoje", description="hoje, amanhã ou data dd/mm.")
    days: int = Field(default=1, ge=1, le=7)


class RunsIn(BaseModel):
    status: Literal["failed", "success", "running", "any"] = "any"
    period: Literal["today", "week"] = "today"


class MetricsIn(BaseModel):
    period: Literal["today", "week", "month"] = "week"


class ReportIn(BaseModel):
    kind: reports.ReportKind


class NavigateIn(BaseModel):
    target: str = Field(min_length=1, max_length=200, description="Área (ex.: tarefas, agenda) ou nome de projecto.")


class CreateTaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    project: str | None = Field(default=None, description="Id ou nome do projecto.")
    priority: schemas.Priority = "medium"
    due: str | None = Field(default=None, description="hoje, amanhã, dia da semana, dd/mm ou AAAA-MM-DD.")


class CreateNoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=50_000)
    kind: schemas.NoteKind = "note"
    project: str | None = None


class CreateProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ChecklistItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    section: str = Field(default="", max_length=120)


class CreateChecklistIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    items: list[ChecklistItemIn] = Field(default_factory=list, max_length=100)
    template: str | None = Field(default=None, description="Id ou título de um modelo de checklist existente.")
    project: str | None = None


class TaskStatusIn(BaseModel):
    task: str = Field(min_length=1, max_length=300, description="Id ou título (parcial) da tarefa.")
    status: schemas.TaskStatus


class TaskRefIn(BaseModel):
    task: str = Field(min_length=1, max_length=300)


class AutomationRefIn(BaseModel):
    automation: str = Field(min_length=1, max_length=200)


class FocusIn(BaseModel):
    project: str | None = None


# --------------------------------------------------------------------------- Leitura


def _overview(db: Session, _: EmptyIn) -> ToolResult:
    d = metrics.dashboard(db)
    c = d["counters"]
    data = {
        "counters": c,
        "alerts": d["alerts"],
        "priority_tasks": [brief_task(db, t) for t in d["priority_tasks"]],
        "active_projects": [
            {"id": p.id, "name": p.name, "status": p.status, "progress": p.progress.percent if p.progress else None}
            for p in d["active_projects"]
        ],
    }
    msg = (
        f"{c['active_projects']} projectos activos, {c['pending_tasks']} tarefas pendentes, "
        f"{c['overdue_tasks']} atrasadas e {c['done_today']} concluídas hoje."
    )
    return ToolResult(msg, data)


def _search(db: Session, p: SearchIn) -> ToolResult:
    hits = search(db, p.query, limit=10)
    if not hits:
        return ToolResult(f"Não encontrei resultados para «{p.query}».", [])
    labels = "; ".join(f"{h.get('title')}" for h in hits[:5])
    return ToolResult(f"Encontrei {len(hits)} resultado(s) para «{p.query}»: {labels}.", hits)


def _list_projects(db: Session, _: EmptyIn) -> ToolResult:
    page = project_service.list_projects(db, limit=50)
    items = [
        {
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "priority": p.priority,
            "progress": p.progress.percent if p.progress else None,
            "overdue_tasks": p.progress.overdue_tasks if p.progress else 0,
        }
        for p in page.items
    ]
    if not items:
        return ToolResult("Não tem projectos registados.", [])
    names = ", ".join(str(i["name"]) for i in items[:8])
    return ToolResult(f"Tem {len(items)} projecto(s): {names}.", items)


def project_blockers(db: Session, p: Project) -> dict[str, Any]:
    """Factos que explicam o que está a bloquear um projecto."""
    blocked_tasks = task_service.list_tasks(db, project_id=p.id, status=["blocked"], limit=20).items
    overdue = task_service.list_tasks(db, project_id=p.id, due="overdue", limit=20).items
    open_ids = select(Task.id).where(Task.status != "done")
    waiting = list(
        db.scalars(
            select(Task)
            .join(TaskDependency, TaskDependency.task_id == Task.id)
            .where(
                Task.project_id == p.id,
                Task.status != "done",
                Task.archived_at.is_(None),
                TaskDependency.depends_on_id.in_(open_ids),
            )
            .distinct()
            .limit(20)
        )
    )
    return {
        "project_blocked_reason": p.blocked_reason if p.status == "blocked" else "",
        "blocked_tasks": [{"title": t.title, "reason": t.blocked_reason} for t in blocked_tasks],
        "overdue_tasks": [t.title for t in overdue],
        "waiting_dependencies": [t.title for t in waiting],
    }


def _get_project(db: Session, p: ProjectRefIn) -> ToolResult:
    proj = resolve_project(db, p.project, include_archived=True)
    out = project_service.enrich(db, [proj])[0]
    prog = out.progress
    blockers = project_blockers(db, proj)
    next_tasks = [
        brief_task(db, t) for t in task_service.list_tasks(db, project_id=proj.id, status=["todo", "in_progress"]).items
    ][:5]
    parts = [f"O projecto {proj.name} está {PROJECT_STATUS_LABEL.get(proj.status, proj.status)}"]
    if prog and prog.percent is not None:
        parts.append(f"com {prog.percent}% das tarefas concluídas ({prog.tasks_done} de {prog.tasks_total})")
    else:
        parts.append("e ainda não tem tarefas para medir o progresso")
    msg = " ".join(parts) + "."
    if proj.due_date:
        msg += f" Data de fim prevista: {proj.due_date.strftime('%d/%m/%Y')}."
    if blockers["project_blocked_reason"]:
        msg += f" Motivo do bloqueio: {blockers['project_blocked_reason']}."
    if blockers["overdue_tasks"]:
        msg += f" Tem {len(blockers['overdue_tasks'])} tarefa(s) atrasada(s)."
    if proj.description:
        msg += f" Descrição: {proj.description[:300]}"
    data = {
        "id": proj.id,
        "name": proj.name,
        "status": proj.status,
        "priority": proj.priority,
        "due_date": proj.due_date.isoformat() if proj.due_date else None,
        "progress": prog.model_dump() if prog else None,
        "description": proj.description[:2000],
        "blockers": blockers,
        "next_tasks": next_tasks,
        "stale": out.stale,
    }
    return ToolResult(msg, data, entity={"type": "project", "id": proj.id, "label": proj.name})


def _explain_blockers(db: Session, p: ProjectRefIn) -> ToolResult:
    proj = resolve_project(db, p.project, include_archived=True)
    b = project_blockers(db, proj)
    lines: list[str] = []
    if b["project_blocked_reason"]:
        lines.append(f"O projecto está marcado como bloqueado: {b['project_blocked_reason']}.")
    for t in b["blocked_tasks"][:5]:
        lines.append(f"A tarefa «{t['title']}» está bloqueada" + (f": {t['reason']}." if t["reason"] else "."))
    if b["waiting_dependencies"]:
        lines.append(
            f"{len(b['waiting_dependencies'])} tarefa(s) esperam por dependências em aberto, "
            f"por exemplo «{b['waiting_dependencies'][0]}»."
        )
    if b["overdue_tasks"]:
        lines.append(f"Há {len(b['overdue_tasks'])} tarefa(s) atrasada(s), por exemplo «{b['overdue_tasks'][0]}».")
    if not lines:
        msg = (
            f"Não encontrei bloqueios registados no projecto {proj.name}: "
            "sem motivo de bloqueio, tarefas bloqueadas, dependências em aberto ou atrasos."
        )
    else:
        msg = f"No projecto {proj.name}: " + " ".join(lines)
    return ToolResult(msg, b, entity={"type": "project", "id": proj.id, "label": proj.name})


def _list_tasks(db: Session, p: ListTasksIn) -> ToolResult:
    project_id = resolve_project(db, p.project).id if p.project else None
    status: list[str] | None = list(p.status) if p.status else None
    if status is None and p.due != "overdue":
        status = ["todo", "in_progress", "blocked"]
    page = task_service.list_tasks(db, project_id=project_id, status=status, due=p.due, limit=p.limit)
    items = [brief_task(db, t) for t in page.items]
    if not items:
        what = {"overdue": "atrasadas", "today": "com prazo hoje", "week": "com prazo esta semana"}.get(p.due or "", "")
        return ToolResult(f"Não há tarefas {what}.".replace("  ", " "), [])
    lines = "; ".join(_task_line(db, t) for t in page.items[:5])
    more = f" e mais {page.total - 5}" if page.total > 5 else ""
    return ToolResult(f"{page.total} tarefa(s): {lines}{more}.", items)


def _get_note(db: Session, p: NoteRefIn) -> ToolResult:
    n = db.get(Note, p.note_id)
    if n is None:
        raise NotFound("Nota não encontrada.")
    return ToolResult(
        f"Nota «{n.title}».",
        {"id": n.id, "title": n.title, "kind": n.kind, "content": n.content[:20000]},
        entity={"type": "note", "id": n.id, "label": n.title},
    )


def _agenda(db: Session, p: AgendaIn) -> ToolResult:
    due = parse_due(db, p.day)
    assert due is not None
    day = due.astimezone(local_tz(db)).date()
    a = agenda_service.agenda(db, day, p.days)
    events = a["events"]
    tasks = a["tasks"]
    assert isinstance(events, list) and isinstance(tasks, list)
    tz = local_tz(db)
    ev = [{"title": e.title, "start": e.start_at.astimezone(tz).strftime("%H:%M"), "kind": e.kind} for e in events]
    tk = [brief_task(db, t) for t in tasks if t.status != "done"]
    label = "hoje" if day == local_today(db) else day.strftime("%d/%m")
    if not ev and not tk:
        return ToolResult(f"Não tem compromissos nem prazos para {label}.", {"events": [], "tasks": []})
    parts = []
    if ev:
        parts.append(f"{len(ev)} compromisso(s): " + "; ".join(f"{e['start']} {e['title']}" for e in ev[:6]))
    if tk:
        parts.append(f"{len(tk)} tarefa(s) com prazo: " + "; ".join(t["title"] for t in tk[:6]))
    return ToolResult(f"Agenda de {label}: " + ". ".join(parts) + ".", {"events": ev, "tasks": tk})


def _runs(db: Session, p: RunsIn) -> ToolResult:
    today = local_today(db)
    start, _ = day_bounds(db, today if p.period == "today" else today - timedelta(days=6))
    stmt = (
        select(AutomationRun, Automation.name)
        .join(Automation, Automation.id == AutomationRun.automation_id)
        .where(AutomationRun.started_at >= start)
        .order_by(AutomationRun.started_at.desc())
        .limit(30)
    )
    if p.status == "running":
        stmt = stmt.where(AutomationRun.status.in_(["pending", "running"]))
    elif p.status != "any":
        stmt = stmt.where(AutomationRun.status == p.status)
    rows = db.execute(stmt).all()
    tz = local_tz(db)
    items = [
        {
            "id": r.id,
            "automation": name,
            "status": r.status,
            "started": r.started_at.astimezone(tz).strftime("%d/%m %H:%M"),
            "error": r.error[:300],
        }
        for r, name in rows
    ]
    period = "hoje" if p.period == "today" else "nos últimos 7 dias"
    if not items:
        what = {"failed": "falhadas", "success": "concluídas", "running": "em curso"}.get(p.status, "")
        return ToolResult(f"Não houve execuções de automações {what} {period}.".replace("  ", " "), [])
    if p.status == "failed":
        detail = "; ".join(f"{i['automation']} ({i['started']}): {i['error'] or 'sem detalhe'}" for i in items[:4])
        return ToolResult(f"{len(items)} execução(ões) falhada(s) {period}: {detail}.", items)
    counts: dict[str, int] = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    summary = ", ".join(f"{v} {reports.RUN_STATUS_LABEL.get(k, k)}" for k, v in counts.items())
    return ToolResult(f"{len(items)} execução(ões) {period}: {summary}.", items)


def _metrics(db: Session, p: MetricsIn) -> ToolResult:
    today = local_today(db)
    start = today - timedelta(days={"today": 0, "week": 6, "month": 29}[p.period])
    m = metrics.metrics(db, start, today)
    t = m["totals"]
    label = {"today": "hoje", "week": "nos últimos 7 dias", "month": "nos últimos 30 dias"}[p.period]
    msg = (
        f"{label.capitalize()}: {t['done']} tarefa(s) concluída(s), {t['created']} criada(s), "
        f"{t['focus_minutes']} minutos de foco registados. {t['overdue_now']} tarefa(s) atrasada(s) neste momento."
    )
    return ToolResult(msg, {"totals": t, "done_by_project": m["done_by_project"], "sources": m["sources"]})


def _report(db: Session, p: ReportIn) -> ToolResult:
    r = reports.build(db, p.kind)
    return ToolResult(r.speech, r.to_dict(), report=r)


AREA_LABEL = {
    "/": "o painel",
    "/projects": "projectos",
    "/tasks": "tarefas",
    "/agenda": "a agenda",
    "/notes": "as notas",
    "/knowledge": "o conhecimento",
    "/automations": "as automações",
    "/metrics": "o desempenho",
    "/settings": "as definições",
}


def _navigate(db: Session, p: NavigateIn) -> ToolResult:
    t = norm(p.target).removeprefix("o ").removeprefix("a ").removeprefix("os ").removeprefix("as ")
    t = t.removeprefix("projecto ").removeprefix("projeto ").strip()
    if t in ROUTES:
        route = ROUTES[t]
        return ToolResult(f"A abrir {AREA_LABEL.get(route, t)}.", {"route": route}, navigate=route)
    try:
        proj = resolve_project(db, t)
    except NotFound:
        from ..system import macos

        app = macos.find_app(t)
        if app is None:
            raise NotFound(f"Não encontrei nenhuma área, projecto ou aplicação chamada «{p.target}».") from None
        return ToolResult("", delegate=("open_app", {"name": app.stem}))
    return ToolResult(
        f"A abrir o projecto {proj.name}.",
        {"route": f"/projects/{proj.id}"},
        entity={"type": "project", "id": proj.id, "label": proj.name},
        navigate=f"/projects/{proj.id}",
    )


# --------------------------------------------------------------------------- Escrita


def _create_task(db: Session, p: CreateTaskIn) -> ToolResult:
    project_id = resolve_project(db, p.project).id if p.project else None
    t = task_service.create_task(
        db,
        schemas.TaskCreate(
            title=p.title,
            description=p.description,
            project_id=project_id,
            priority=p.priority,
            due_at=parse_due(db, p.due),
        ),
    )
    out = task_service.enrich(db, [t])[0]
    extra = []
    if out.project_name:
        extra.append(f"no projecto {out.project_name}")
    if t.due_at:
        extra.append(f"com prazo {_fmt_due(db, t.due_at)}")
    return ToolResult(
        f"Tarefa criada: «{t.title}»" + (f", {', '.join(extra)}" if extra else "") + ".",
        {"task_id": t.id},
        entity={"type": "task", "id": t.id, "label": t.title},
    )


def _describe_task(db: Session, p: CreateTaskIn) -> list[str]:
    d = [f"Título: {p.title}", f"Prioridade: {PRIORITY_LABEL[p.priority]}"]
    if p.project:
        d.append(f"Projecto: {resolve_project(db, p.project).name}")
    if p.due:
        d.append(f"Prazo: {_fmt_due(db, parse_due(db, p.due))}")
    return d


def _create_note(db: Session, p: CreateNoteIn) -> ToolResult:
    project_id = resolve_project(db, p.project).id if p.project else None
    n = note_service.create_note(
        db,
        schemas.NoteCreate(
            title=p.title, content=p.content, kind=p.kind, project_id=project_id, in_knowledge_base=p.kind != "note"
        ),
    )
    label = {"idea": "Ideia registada", "decision": "Decisão registada"}.get(p.kind, "Nota criada")
    return ToolResult(
        f"{label}: «{n.title}».", {"note_id": n.id}, entity={"type": "note", "id": n.id, "label": n.title}
    )


def _create_project(db: Session, p: CreateProjectIn) -> ToolResult:
    proj = project_service.create_project(
        db, schemas.ProjectCreate(name=p.name, description=p.description, status="active")
    )
    return ToolResult(
        f"Projecto criado: {proj.name}.",
        {"project_id": proj.id},
        entity={"type": "project", "id": proj.id, "label": proj.name},
        navigate=f"/projects/{proj.id}",
    )


def find_template(db: Session, ref: str) -> Checklist | None:
    templates = list(db.scalars(select(Checklist).where(Checklist.is_template.is_(True))))
    if not templates:
        return None
    try:
        return _pick(templates, lambda c: c.title, ref, "modelo")
    except (NotFound, Ambiguous):
        pass
    # Sobreposição de palavras significativas (ex.: «publicar uma API» ↔ «Publicação de uma aplicação»).
    stop = {"de", "da", "do", "uma", "um", "para", "a", "o", "e", "em", "com", "dos", "das"}

    def stems(s: str) -> set[str]:
        return {w[:5] for w in norm(s).split() if w not in stop and len(w) > 2}

    want = stems(ref)
    scored = sorted(((len(want & stems(c.title)), c) for c in templates), key=lambda x: -x[0])
    if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


def _create_checklist(db: Session, p: CreateChecklistIn) -> ToolResult:
    project_id = resolve_project(db, p.project).id if p.project else None
    tpl = find_template(db, p.template) if p.template else None
    if p.template and tpl is None:
        raise NotFound(f"Não encontrei um modelo de checklist para «{p.template}».")
    if tpl is not None and not p.items:
        c = checklist_service.duplicate(db, tpl.id, as_template=False, project_id=project_id, title=p.title)
        msg = f"Checklist «{c.title}» criada a partir do modelo «{tpl.title}», com {len(c.items)} itens."
    else:
        if not p.items:
            raise ValidationFailed("A checklist precisa de itens ou de um modelo.")
        c = checklist_service.create_checklist(
            db,
            schemas.ChecklistCreate(
                title=p.title,
                project_id=project_id,
                items=[schemas.ChecklistItemIn(text=i.text, section=i.section) for i in p.items],
            ),
        )
        msg = f"Checklist «{c.title}» criada com {len(c.items)} itens."
    return ToolResult(
        msg,
        {"checklist_id": c.id, "items": [i.text for i in c.items][:30], "template": tpl.title if tpl else None},
        entity={"type": "checklist", "id": c.id, "label": c.title},
        navigate=f"/templates/{c.id}",
    )


def _describe_checklist(db: Session, p: CreateChecklistIn) -> list[str]:
    d = [f"Título: {p.title}"]
    if p.template:
        tpl = find_template(db, p.template)
        d.append(f"Modelo: {tpl.title if tpl else 'não encontrado'}")
    d += [f"• {i.text}" for i in p.items[:12]]
    return d


def _set_task_status(db: Session, p: TaskStatusIn) -> ToolResult:
    t = resolve_task(db, p.task, open_only=p.status != "todo")
    old = t.status
    t = task_service.change_status(db, t.id, p.status)
    return ToolResult(
        f"Tarefa «{t.title}»: {STATUS_LABEL.get(old, old)} → {STATUS_LABEL[t.status]}.",
        {"task_id": t.id, "status": t.status},
        entity={"type": "task", "id": t.id, "label": t.title},
    )


def _describe_status(db: Session, p: TaskStatusIn) -> list[str]:
    t = resolve_task(db, p.task, open_only=p.status != "todo")
    return [f"Tarefa: {t.title}", f"Estado: {STATUS_LABEL.get(t.status, t.status)} → {STATUS_LABEL[p.status]}"]


def _start_focus(db: Session, p: FocusIn) -> ToolResult:
    project_id = resolve_project(db, p.project).id if p.project else None
    s = task_service.start_focus(db, schemas.FocusStart(project_id=project_id))
    return ToolResult("Sessão de foco iniciada.", {"focus_id": s.id})


def _stop_focus(db: Session, _: EmptyIn) -> ToolResult:
    s = task_service.stop_focus(db)
    return ToolResult(f"Sessão de foco registada: {s.duration_seconds // 60} minutos.", {"focus_id": s.id})


def _run_automation(db: Session, p: AutomationRefIn) -> ToolResult:
    from ..automation import engine

    a = resolve_automation(db, p.automation)
    if not a.enabled:
        raise ValidationFailed(f"A automação «{a.name}» está desactivada. Active-a antes de a executar.")
    run_id = engine.execute(a.id, "manual", {"source": "assistant"})
    if run_id is None:
        return ToolResult(f"A automação «{a.name}» já estava em execução; não foi repetida.", {"run_id": None})
    run = db.get(AutomationRun, run_id)
    if run is not None:
        db.refresh(run)
    status = run.status if run else "unknown"
    if status == "failed":
        return ToolResult(
            f"A automação «{a.name}» falhou: {run.error if run else ''}".strip(),
            {"run_id": run_id, "status": status},
        )
    return ToolResult(
        f"Automação «{a.name}» executada ({reports.RUN_STATUS_LABEL.get(status, status)}).",
        {"run_id": run_id, "status": status},
        navigate=f"/automations/{a.id}",
    )


def _describe_automation(db: Session, p: AutomationRefIn) -> list[str]:
    a = resolve_automation(db, p.automation)
    return [f"Automação: {a.name}", f"Estado: {'activa' if a.enabled else 'desactivada'}", a.description[:200]]


def _delete_task(db: Session, p: TaskRefIn) -> ToolResult:
    t = resolve_task(db, p.task, open_only=False)
    title = t.title
    task_service.delete_task(db, t.id, confirm=True)
    return ToolResult(f"Tarefa eliminada: «{title}».", {"task_id": p.task})


def _describe_delete_task(db: Session, p: TaskRefIn) -> list[str]:
    t = resolve_task(db, p.task, open_only=False)
    subtasks = db.scalar(select(func.count(Task.id)).where(Task.parent_id == t.id)) or 0
    d = [f"Eliminar definitivamente a tarefa «{t.title}»", f"Estado actual: {STATUS_LABEL.get(t.status, t.status)}"]
    if subtasks:
        d.append(f"Também serão eliminadas {subtasks} subtarefa(s).")
    d.append("Esta operação não pode ser desfeita (só por restauro de backup).")
    return d


def _archive_project(db: Session, p: ProjectRefIn) -> ToolResult:
    proj = resolve_project(db, p.project)
    project_service.archive_project(db, proj.id, True)
    return ToolResult(f"Projecto arquivado: {proj.name}.", {"project_id": proj.id})


def _describe_archive(db: Session, p: ProjectRefIn) -> list[str]:
    proj = resolve_project(db, p.project)
    n = db.scalar(select(func.count(Task.id)).where(Task.project_id == proj.id, Task.status != "done")) or 0
    return [
        f"Arquivar o projecto «{proj.name}»",
        f"{n} tarefa(s) em aberto deixam de aparecer nas listas activas.",
        "Pode ser reactivado mais tarde a partir da lista de projectos arquivados.",
    ]


def _delete_project(db: Session, p: ProjectRefIn) -> ToolResult:
    proj = resolve_project(db, p.project, include_archived=True)
    name = proj.name
    project_service.delete_project(db, proj.id, confirm=True)
    return ToolResult(f"Projecto eliminado: {name}.", {"project_id": p.project}, navigate="/projects")


def _describe_delete_project(db: Session, p: ProjectRefIn) -> list[str]:
    proj = resolve_project(db, p.project, include_archived=True)
    n = db.scalar(select(func.count(Task.id)).where(Task.project_id == proj.id)) or 0
    return [
        f"Eliminar definitivamente o projecto «{proj.name}»",
        f"{n} tarefa(s) ficam sem projecto (não são apagadas); marcos e links do projecto são eliminados.",
        "Esta operação não pode ser desfeita (só por restauro de backup).",
    ]


TOOLS: list[Tool] = [
    Tool(
        "get_overview",
        "Resumo actual: contadores, tarefas prioritárias, projectos activos e alertas.",
        EmptyIn,
        "read",
        _overview,
    ),
    Tool("search", "Pesquisa textual em projectos, tarefas, notas, eventos e automações.", SearchIn, "read", _search),
    Tool("list_projects", "Lista projectos não arquivados com estado e progresso.", EmptyIn, "read", _list_projects),
    Tool(
        "get_project",
        "Detalhes de um projecto: estado, progresso, bloqueios e próximas tarefas.",
        ProjectRefIn,
        "read",
        _get_project,
    ),
    Tool(
        "explain_project_blockers",
        "Explica o que está a bloquear um projecto, com base nos registos.",
        ProjectRefIn,
        "read",
        _explain_blockers,
    ),
    Tool(
        "list_tasks", "Lista tarefas com filtros opcionais (projecto, estado, prazo).", ListTasksIn, "read", _list_tasks
    ),
    Tool("get_note", "Lê o conteúdo de uma nota pelo id.", NoteRefIn, "read", _get_note),
    Tool("get_agenda", "Compromissos e prazos de um dia.", AgendaIn, "read", _agenda),
    Tool(
        "list_automation_runs",
        "Execuções de automações (hoje ou 7 dias), opcionalmente por estado.",
        RunsIn,
        "read",
        _runs,
    ),
    Tool("get_metrics", "Métricas de desempenho registadas (tarefas, foco, atrasos).", MetricsIn, "read", _metrics),
    Tool(
        "build_report",
        "Relatório estruturado com dados reais: daily, weekly, projects, next_steps, automations, problems.",
        ReportIn,
        "read",
        _report,
    ),
    Tool("navigate", "Abre uma área da aplicação ou um projecto na interface.", NavigateIn, "read", _navigate),
    Tool(
        "create_task",
        "Cria uma tarefa.",
        CreateTaskIn,
        "create",
        _create_task,
        _describe_task,
        lambda db, p: f"Criar tarefa «{p.title}»",
    ),
    Tool(
        "create_note",
        "Cria uma nota, ideia ou decisão.",
        CreateNoteIn,
        "create",
        _create_note,
        None,
        lambda db, p: f"Registar {'ideia' if p.kind == 'idea' else 'nota'} «{p.title}»",
    ),
    Tool(
        "create_project",
        "Cria um projecto activo.",
        CreateProjectIn,
        "create",
        _create_project,
        None,
        lambda db, p: f"Criar projecto «{p.name}»",
    ),
    Tool(
        "create_checklist",
        "Cria uma checklist a partir de itens ou de um modelo existente.",
        CreateChecklistIn,
        "create",
        _create_checklist,
        _describe_checklist,
        lambda db, p: f"Criar checklist «{p.title}»",
    ),
    Tool(
        "start_focus",
        "Inicia uma sessão de foco.",
        FocusIn,
        "create",
        _start_focus,
        None,
        lambda db, p: "Iniciar sessão de foco",
    ),
    Tool(
        "stop_focus",
        "Termina a sessão de foco activa.",
        EmptyIn,
        "update",
        _stop_focus,
        None,
        lambda db, p: "Terminar sessão de foco",
    ),
    Tool(
        "update_task_status",
        "Altera o estado de uma tarefa (incluindo concluir).",
        TaskStatusIn,
        "update",
        _set_task_status,
        _describe_status,
        lambda db, p: f"Marcar «{p.task}» como {STATUS_LABEL[p.status]}",
    ),
    Tool(
        "run_automation",
        "Executa manualmente uma automação activa.",
        AutomationRefIn,
        "update",
        _run_automation,
        _describe_automation,
        lambda db, p: f"Executar a automação «{p.automation}»",
    ),
    Tool(
        "archive_project",
        "Arquiva um projecto.",
        ProjectRefIn,
        "destructive",
        _archive_project,
        _describe_archive,
        lambda db, p: f"Arquivar o projecto «{p.project}»",
    ),
    Tool(
        "delete_task",
        "Elimina definitivamente uma tarefa.",
        TaskRefIn,
        "destructive",
        _delete_task,
        _describe_delete_task,
        lambda db, p: f"Eliminar a tarefa «{p.task}»",
    ),
    Tool(
        "delete_project",
        "Elimina definitivamente um projecto.",
        ProjectRefIn,
        "destructive",
        _delete_project,
        _describe_delete_project,
        lambda db, p: f"Eliminar o projecto «{p.project}»",
    ),
]
# --------------------------------------------------------------------------- Sistema e actividade


class AppIn(BaseModel):
    name: str = Field(min_length=1, max_length=120, description="Nome da aplicação (ex.: Visual Studio Code).")


class UrlIn(BaseModel):
    target: str = Field(min_length=1, max_length=2000, description="Endereço http(s) ou texto a pesquisar.")


class PathIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class VolumeIn(BaseModel):
    level: int = Field(ge=0, le=100)


class ShellIn(BaseModel):
    command: str = Field(min_length=1, max_length=2000)


class ActivityIn(BaseModel):
    app: str | None = Field(default=None, max_length=120, description="Filtrar por aplicação (opcional).")


def _system_error(e: Exception) -> ValidationFailed:
    return ValidationFailed(str(e) or "A acção no sistema falhou.")


def _sys_allowed(db: Session, key: str) -> None:
    cfg = get_all_settings(db)["system"]
    if not cfg.get(key, False):
        what = {"allow_apps": "abrir ou fechar aplicações", "allow_shell": "executar comandos de terminal"}[key]
        raise ValidationFailed(f"A permissão para {what} está desligada (Definições → Sistema e comandos).")


def _open_app(db: Session, p: AppIn) -> ToolResult:
    from ..system import macos

    _sys_allowed(db, "allow_apps")
    try:
        name = macos.open_app(p.name)
    except (LookupError, RuntimeError) as e:
        raise _system_error(e) from e
    return ToolResult(f"A abrir {name}.", {"app": name})


def _quit_app(db: Session, p: AppIn) -> ToolResult:
    from ..system import macos

    _sys_allowed(db, "allow_apps")
    try:
        name = macos.quit_app(p.name)
    except (LookupError, RuntimeError) as e:
        raise _system_error(e) from e
    return ToolResult(
        f"Pedi ao {name} para fechar. Se tiver trabalho por guardar, a aplicação vai perguntar.", {"app": name}
    )


def _running_apps(db: Session, _: EmptyIn) -> ToolResult:
    from ..system import macos

    apps = macos.running_apps()
    names = [a["name"] for a in apps]
    return ToolResult(f"Tem {len(names)} aplicações abertas: {', '.join(names[:12])}.", apps)


def _open_url(db: Session, p: UrlIn) -> ToolResult:
    from ..system import macos

    try:
        url = macos.open_url(p.target)
    except RuntimeError as e:
        raise _system_error(e) from e
    what = "a pesquisa" if "google.com/search" in url else url
    return ToolResult(f"A abrir {what} no browser.", {"url": url})


def _open_path(db: Session, p: PathIn) -> ToolResult:
    from ..system import macos

    try:
        path = macos.open_path(p.path)
    except (LookupError, PermissionError, RuntimeError) as e:
        raise _system_error(e) from e
    return ToolResult(f"A abrir {path}.", {"path": path})


def _set_volume(db: Session, p: VolumeIn) -> ToolResult:
    from ..system import macos

    try:
        level = macos.set_volume(p.level)
    except RuntimeError as e:
        raise _system_error(e) from e
    return ToolResult(f"Volume ajustado para {level}%.", {"level": level})


def _system_status(db: Session, _: EmptyIn) -> ToolResult:
    from ..system import macos

    st = macos.system_status()
    return ToolResult(macos.status_sentence(st), st)


def _run_shell(db: Session, p: ShellIn) -> ToolResult:
    from ..system import macos

    _sys_allowed(db, "allow_shell")
    try:
        out = macos.run_shell(p.command)
    except (PermissionError, ValueError, RuntimeError) as e:
        raise _system_error(e) from e
    first = (out["stdout"] or out["stderr"]).strip().splitlines()[:6]
    status = "terminou sem erros" if out["exit_code"] == 0 else f"terminou com o código {out['exit_code']}"
    msg = f"O comando {status}." + (" Resultado: " + " | ".join(first) if first else " Sem saída.")
    return ToolResult(msg, out)


def _describe_shell(db: Session, p: ShellIn) -> list[str]:
    from ..system import macos

    d = [f"Comando: {p.command}", "Pasta: a sua pasta pessoal · tempo limite 30 s · sem sudo"]
    try:
        macos.check_command(p.command)
    except (PermissionError, ValueError) as e:
        d.append(str(e))
    if not get_all_settings(db)["system"].get("allow_shell"):
        d.append("A execução de comandos está desligada nas Definições: a confirmação vai falhar.")
    return d


def _activity_today(db: Session, p: ActivityIn) -> ToolResult:
    from ..activity import insights

    s = insights.summarize(db)
    if p.app:
        want = norm(p.app)
        hit = [a for a in s["apps"] if want in norm(a["app"])]
        if not hit:
            return ToolResult(f"Não há tempo registado hoje em «{p.app}».", s)
        return ToolResult(f"Hoje passou {insights.fmt_duration(hit[0]['seconds'])} em {hit[0]['app']}.", s)
    return ToolResult(insights.summary_sentence(s), s)


def _activity_patterns(db: Session, _: EmptyIn) -> ToolResult:
    from ..activity import insights

    p = insights.patterns(db)
    return ToolResult(insights.patterns_sentence(p), p)


def _git_today(db: Session, _: EmptyIn) -> ToolResult:
    from ..activity import insights

    folders = list(get_all_settings(db)["activity"].get("git_folders") or [])
    if not folders:
        return ToolResult("Não tenho pastas de projectos configuradas para ler o Git (Actividade → Privacidade).", [])
    repos = insights.git_activity(folders)
    if not repos:
        return ToolResult("Não encontrei commits seus hoje nas pastas configuradas.", [])
    total = sum(len(r["commits"]) for r in repos)
    detail = "; ".join(f"{r['repo']}: {len(r['commits'])} (último: «{r['commits'][0]['message']}»)" for r in repos[:4])
    return ToolResult(f"Hoje fez {total} commit(s) em {len(repos)} repositório(s). {detail}.", repos)


TOOLS += [
    Tool(
        "open_app",
        "Abre uma aplicação instalada no Mac.",
        AppIn,
        "system",
        _open_app,
        None,
        lambda db, p: f"Abrir a aplicação «{p.name}»",
    ),
    Tool(
        "quit_app",
        "Pede a uma aplicação aberta para fechar (como ⌘Q).",
        AppIn,
        "update",
        _quit_app,
        lambda db, p: [f"Fechar «{p.name}»", "A aplicação pode pedir para guardar alterações."],
        lambda db, p: f"Fechar a aplicação «{p.name}»",
    ),
    Tool("running_apps", "Lista as aplicações abertas.", EmptyIn, "read", _running_apps),
    Tool(
        "open_url",
        "Abre um site ou pesquisa um texto no browser.",
        UrlIn,
        "system",
        _open_url,
        None,
        lambda db, p: f"Abrir «{p.target}» no browser",
    ),
    Tool(
        "open_path",
        "Abre uma pasta ou ficheiro da pasta pessoal.",
        PathIn,
        "system",
        _open_path,
        None,
        lambda db, p: f"Abrir {p.path}",
    ),
    Tool(
        "set_volume",
        "Ajusta o volume do Mac (0–100).",
        VolumeIn,
        "system",
        _set_volume,
        None,
        lambda db, p: f"Pôr o volume a {p.level}%",
    ),
    Tool("system_status", "Estado do Mac: bateria, disco, aplicações abertas, carga.", EmptyIn, "read", _system_status),
    Tool(
        "run_shell",
        "Executa um comando de terminal (desligado por omissão; exige sempre confirmação).",
        ShellIn,
        "destructive",
        _run_shell,
        _describe_shell,
        lambda db, p: f"Executar no terminal: {p.command}",
    ),
    Tool(
        "activity_today",
        "O que o utilizador fez hoje no computador (tempo por aplicação e projecto).",
        ActivityIn,
        "read",
        _activity_today,
    ),
    Tool(
        "activity_patterns",
        "Padrões de trabalho dos últimos 14 dias (hora de início, horas intensas).",
        EmptyIn,
        "read",
        _activity_patterns,
    ),
    Tool("git_today", "Commits do utilizador hoje nas pastas de projectos configuradas.", EmptyIn, "read", _git_today),
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def needs_confirmation(db: Session, tool: Tool, origin: Literal["local", "ai"]) -> bool:
    """Leitura: nunca. Destrutivas: sempre. Restantes: conforme as Definições.

    Pedidos interpretados por IA (origem «ai») exigem sempre confirmação para escrever,
    porque a interpretação do modelo pode não corresponder à intenção do utilizador.
    """
    if tool.risk == "read":
        return False
    if tool.risk == "system" and origin == "local":
        return bool(get_all_settings(db)["system"].get("confirm_system", False))
    if tool.risk == "destructive" or origin == "ai":
        return True
    cfg = get_all_settings(db)["assistant"]
    if tool.risk == "create":
        return bool(cfg.get("confirm_creates", False))
    return bool(cfg.get("confirm_updates", True))


def definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": f"{t.description} [risco: {RISK_LABEL[t.risk]}]",
            "input_schema": t.params.model_json_schema(),
        }
        for t in TOOLS
    ]


def utc_now() -> datetime:
    return utcnow()
