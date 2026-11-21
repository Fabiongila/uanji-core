"""Catálogo de acções internas permitidas nas automações.

Cada acção tem parâmetros validados por Pydantic e uma função de execução. Não existe
nenhuma acção de shell, acesso a ficheiros arbitrários ou avaliação de código.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..models import FocusSession, Task, utcnow
from ..services import notes as note_service
from ..services import notifications as notification_service
from ..services import projects as project_service
from ..services import tasks as task_service
from ..services.common import day_bounds, local_today, log_activity


class RecoverableError(Exception):
    """Falha temporária: o motor pode repetir a etapa."""


class CreateTaskParams(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    project_id: str | None = None
    priority: schemas.Priority = "medium"
    due_in_days: int | None = Field(default=None, ge=0, le=365)


class UpdateTaskStatusParams(BaseModel):
    task_id: str = Field(min_length=1)
    status: schemas.TaskStatus
    blocked_reason: str | None = Field(default=None, max_length=2000)


class UpdateProjectStatusParams(BaseModel):
    project_id: str = Field(min_length=1)
    status: schemas.ProjectStatus
    blocked_reason: str | None = Field(default=None, max_length=2000)


class CreateNoteParams(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=50_000)
    kind: schemas.NoteKind = "note"
    project_id: str | None = None


class LogEventParams(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class GenerateSummaryParams(BaseModel):
    scope: Literal["today", "week"] = "today"
    save_as_note: bool = True
    project_id: str | None = None


class NotifyParams(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=2000)
    level: Literal["info", "warning", "error"] = "info"


class SpeakParams(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class CallWebhookParams(BaseModel):
    url: str = Field(min_length=8, max_length=2000, pattern=r"^https?://")
    message: str = Field(default="", max_length=4000)


class RunAutomationParams(BaseModel):
    automation_id: str = Field(min_length=1)


@dataclass(frozen=True)
class ActionSpec:
    name: str
    label: str
    description: str
    params: type[BaseModel]
    run: Callable[[Session, Any, dict[str, Any]], dict[str, Any]]
    # Altera dados persistentes do utilizador (registado e indicado na interface).
    mutates: bool
    # Pode ser desfeita automaticamente? Nenhuma acção actual o garante.
    reversible: bool = False
    # «action» altera ou cria dados; «result» comunica o resultado (notificação, voz, webhook, histórico).
    category: Literal["action", "result"] = "action"


def _create_task(db: Session, p: CreateTaskParams, ctx: dict[str, Any]) -> dict[str, Any]:
    due = utcnow() + timedelta(days=p.due_in_days) if p.due_in_days is not None else None
    t = task_service.create_task(
        db,
        schemas.TaskCreate(
            title=p.title, description=p.description, project_id=p.project_id or None, priority=p.priority, due_at=due
        ),
    )
    return {"task_id": t.id, "title": t.title}


def _update_task_status(db: Session, p: UpdateTaskStatusParams, ctx: dict[str, Any]) -> dict[str, Any]:
    t = task_service.change_status(db, p.task_id, p.status, p.blocked_reason)
    return {"task_id": t.id, "status": t.status}


def _update_project_status(db: Session, p: UpdateProjectStatusParams, ctx: dict[str, Any]) -> dict[str, Any]:
    upd = schemas.ProjectUpdate(status=p.status)
    if p.blocked_reason is not None:
        upd.blocked_reason = p.blocked_reason
    pr = project_service.update_project(db, p.project_id, upd)
    return {"project_id": pr.id, "status": pr.status}


def _create_note(db: Session, p: CreateNoteParams, ctx: dict[str, Any]) -> dict[str, Any]:
    n = note_service.create_note(
        db, schemas.NoteCreate(title=p.title, content=p.content, kind=p.kind, project_id=p.project_id or None)
    )
    return {"note_id": n.id, "title": n.title}


def _log_event(db: Session, p: LogEventParams, ctx: dict[str, Any]) -> dict[str, Any]:
    log_activity(db, "automation", ctx["automation"]["id"], "log", p.message[:500])
    return {"logged": True}


def _generate_summary(db: Session, p: GenerateSummaryParams, ctx: dict[str, Any]) -> dict[str, Any]:
    """Resumo local determinístico (sem IA) a partir dos dados reais."""
    today = local_today(db)
    days = 7 if p.scope == "week" else 1
    start_day = today - timedelta(days=days - 1)
    s, e = day_bounds(db, start_day, days)
    q = select(Task).where(Task.completed_at >= s, Task.completed_at < e)
    open_q = select(Task).where(Task.status != "done", Task.archived_at.is_(None))
    if p.project_id:
        q = q.where(Task.project_id == p.project_id)
        open_q = open_q.where(Task.project_id == p.project_id)
    done = db.scalars(q).all()
    now = utcnow()
    overdue = db.scalars(open_q.where(Task.due_at < now)).all()
    focus = (
        db.scalar(
            select(func.coalesce(func.sum(FocusSession.duration_seconds), 0)).where(
                FocusSession.started_at >= s, FocusSession.started_at < e
            )
        )
        or 0
    )
    period = "hoje" if p.scope == "today" else f"de {start_day.isoformat()} a {today.isoformat()}"
    lines = [
        f"# Resumo {period}",
        "",
        f"- Tarefas concluídas: **{len(done)}**",
        f"- Tarefas atrasadas: **{len(overdue)}**",
        f"- Tempo de foco registado: **{int(focus) // 60} min**",
        "",
        "## Concluídas",
        *([f"- {t.title}" for t in done] or ["- (nenhuma)"]),
        "",
        "## Atrasadas",
        *([f"- {t.title}" for t in overdue[:20]] or ["- (nenhuma)"]),
        "",
        "_Gerado localmente pela automação «" + str(ctx["automation"]["name"]) + "»._",
    ]
    content = "\n".join(lines)
    out: dict[str, Any] = {"done": len(done), "overdue": len(overdue), "focus_minutes": int(focus) // 60}
    if p.save_as_note:
        n = note_service.create_note(
            db,
            schemas.NoteCreate(
                title=f"Resumo {period}", content=content, kind="documentation", project_id=p.project_id or None
            ),
        )
        out["note_id"] = n.id
    out["summary"] = content[:2000]
    return out


def _notify(db: Session, p: NotifyParams, ctx: dict[str, Any]) -> dict[str, Any]:
    n = notification_service.create(
        db,
        category="automation",
        title=p.title,
        body=p.body,
        level=p.level,
        link=f"/automations/{ctx['automation']['id']}",
        respect_preferences=False,
    )
    return {"notification_id": n.id if n else None}


def _speak(db: Session, p: SpeakParams, ctx: dict[str, Any]) -> dict[str, Any]:
    """O assistente diz o texto (se a voz estiver activa); fica também como notificação."""
    from ..voice import service as voice_service

    spoken = False
    try:
        svc = voice_service.get()
        if svc.voice_cfg.get("tts_enabled", True) and svc.state in ("off", "wake", "done", "error"):
            svc.speak_text(p.text)
            spoken = True
    except Exception:  # sem voz disponível: a notificação garante que a mensagem chega
        spoken = False
    notification_service.create(
        db,
        category="automation",
        title=p.text[:300],
        link=f"/automations/{ctx['automation']['id']}",
        respect_preferences=False,
    )
    return {"spoken": spoken}


def _call_webhook(db: Session, p: CallWebhookParams, ctx: dict[str, Any]) -> dict[str, Any]:
    """Envia um POST JSON para uma aplicação externa (ex.: Slack, n8n, um servidor próprio)."""
    import httpx

    body = {"automation": ctx["automation"]["name"], "message": p.message, "trigger": ctx.get("trigger", {})}
    try:
        r = httpx.post(p.url, json=body, timeout=10.0)
    except httpx.HTTPError as e:
        raise RecoverableError(f"Sem ligação a {p.url}: {type(e).__name__}") from e
    if r.status_code >= 500:
        raise RecoverableError(f"O destino respondeu {r.status_code}.")
    if r.status_code >= 400:
        from ..errors import ExternalServiceError

        raise ExternalServiceError(f"O destino recusou o pedido ({r.status_code}).")
    return {"status_code": r.status_code}


def _run_automation(db: Session, p: RunAutomationParams, ctx: dict[str, Any]) -> dict[str, Any]:
    from . import engine

    depth = int(db.info.get("automation_depth", 1))
    run_id = engine.execute(p.automation_id, "chained", {"from": ctx["automation"]["id"]}, depth=depth)
    return {"run_id": run_id}


ACTIONS: dict[str, ActionSpec] = {
    a.name: a
    for a in [
        ActionSpec("create_task", "Criar tarefa", "Cria uma nova tarefa.", CreateTaskParams, _create_task, True),
        ActionSpec(
            "update_task_status",
            "Actualizar estado da tarefa",
            "Altera o estado de uma tarefa.",
            UpdateTaskStatusParams,
            _update_task_status,
            True,
        ),
        ActionSpec(
            "update_project_status",
            "Actualizar estado do projecto",
            "Altera o estado de um projecto.",
            UpdateProjectStatusParams,
            _update_project_status,
            True,
        ),
        ActionSpec("create_note", "Criar nota", "Cria uma nota Markdown.", CreateNoteParams, _create_note, True),
        ActionSpec(
            "log_event",
            "Registar evento",
            "Escreve uma entrada no histórico.",
            LogEventParams,
            _log_event,
            False,
            category="result",
        ),
        ActionSpec(
            "generate_summary",
            "Gerar resumo local",
            "Resume tarefas concluídas, atrasadas e foco (sem IA).",
            GenerateSummaryParams,
            _generate_summary,
            True,
        ),
        ActionSpec(
            "notify",
            "Mostrar notificação",
            "Cria uma notificação interna.",
            NotifyParams,
            _notify,
            False,
            category="result",
        ),
        ActionSpec(
            "speak",
            "Falar (assistente)",
            "O assistente diz uma mensagem em voz alta.",
            SpeakParams,
            _speak,
            False,
            category="result",
        ),
        ActionSpec(
            "call_webhook",
            "Chamar webhook externo",
            "Envia um POST JSON para outra aplicação.",
            CallWebhookParams,
            _call_webhook,
            False,
            category="result",
        ),
        ActionSpec(
            "run_automation",
            "Executar outro fluxo",
            "Encadeia outra automação.",
            RunAutomationParams,
            _run_automation,
            True,
        ),
    ]
}


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": a.name,
            "label": a.label,
            "description": a.description,
            "mutates": a.mutates,
            "reversible": a.reversible,
            "category": a.category,
            "schema": a.params.model_json_schema(),
        }
        for a in ACTIONS.values()
    ]
