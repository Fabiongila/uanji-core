"""Interpretador local de comandos da barra de comando (sem IA, determinístico).

Exemplos:
    tarefa Rever PR do backend !alta @amanhã
    projecto Visão computacional LGA
    nota Ideias para o dashboard
    pesquisar fastapi
    ir para tarefas
    foco iniciar | foco parar
    concluir <texto da tarefa>
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..models import Task
from . import notes as note_service
from . import projects as project_service
from . import tasks as task_service
from .common import local_today, local_tz, search

ROUTES = {
    "inicio": "/",
    "dashboard": "/",
    "projectos": "/projects",
    "projetos": "/projects",
    "tarefas": "/tasks",
    "kanban": "/tasks?view=board",
    "agenda": "/agenda",
    "planeamento": "/planning",
    "revisao": "/review",
    "notas": "/notes",
    "conhecimento": "/knowledge",
    "modelos": "/templates",
    "checklists": "/templates",
    "automacoes": "/automations",
    "historico": "/history",
    "desempenho": "/metrics",
    "metricas": "/metrics",
    "integracoes": "/integrations",
    "cofre": "/vault",
    "backups": "/backups",
    "definicoes": "/settings",
    "assistente": "/assistant",
}
PRIORITIES = {"baixa": "low", "media": "medium", "alta": "high", "critica": "critical", "urgente": "critical"}

SUGGESTIONS = [
    {"command": "tarefa ", "label": "Criar tarefa", "hint": "tarefa Título !alta @amanhã"},
    {"command": "projecto ", "label": "Criar projecto", "hint": "projecto Nome"},
    {"command": "nota ", "label": "Criar nota", "hint": "nota Título"},
    {"command": "pesquisar ", "label": "Pesquisar", "hint": "pesquisar termo"},
    {"command": "concluir ", "label": "Concluir tarefa", "hint": "concluir parte do título"},
    {"command": "foco iniciar", "label": "Iniciar sessão de foco", "hint": ""},
    {"command": "foco parar", "label": "Terminar sessão de foco", "hint": ""},
    {"command": "ir para ", "label": "Navegar", "hint": "ir para agenda"},
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _parse_due(db: Session, token: str) -> datetime | None:
    tz = local_tz(db)
    today = local_today(db)
    t = _norm(token)
    end_of_day = time(18, 0)
    if t == "hoje":
        d = today
    elif t == "amanha":
        d = today + timedelta(days=1)
    elif t.startswith("+") and t[1:].rstrip("d").isdigit():
        d = today + timedelta(days=int(t[1:].rstrip("d")))
    else:
        try:
            d = datetime.strptime(token, "%d/%m").date().replace(year=today.year)
        except ValueError:
            try:
                d = datetime.strptime(token, "%Y-%m-%d").date()
            except ValueError:
                return None
    return datetime.combine(d, end_of_day, tzinfo=tz)


def _extract_modifiers(db: Session, text: str) -> tuple[str, str, datetime | None]:
    priority, due = "medium", None
    words = []
    for w in text.split():
        if w.startswith("!") and _norm(w[1:]) in PRIORITIES:
            priority = PRIORITIES[_norm(w[1:])]
        elif w.startswith("@") and (parsed := _parse_due(db, w[1:])):
            due = parsed
        else:
            words.append(w)
    return " ".join(words).strip(), priority, due


def run(db: Session, raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {"kind": "help", "message": "Escreva um comando.", "suggestions": SUGGESTIONS}
    head, _, rest = text.partition(" ")
    h = _norm(head)
    rest = rest.strip()

    if h in ("tarefa", "task", "todo") or (h in ("criar", "nova", "novo") and _norm(rest).startswith("tarefa")):
        if h in ("criar", "nova", "novo"):
            rest = rest.partition(" ")[2]
        title, priority, due = _extract_modifiers(db, rest)
        if not title:
            return {"kind": "error", "message": "Indique o título da tarefa."}
        t = task_service.create_task(db, schemas.TaskCreate(title=title, priority=priority, due_at=due))
        return {
            "kind": "created",
            "entity_type": "task",
            "entity_id": t.id,
            "route": f"/tasks/{t.id}",
            "message": f"Tarefa criada: {t.title}",
        }
    if h in ("projecto", "projeto", "project"):
        if not rest:
            return {"kind": "error", "message": "Indique o nome do projecto."}
        p = project_service.create_project(db, schemas.ProjectCreate(name=rest, status="active"))
        return {
            "kind": "created",
            "entity_type": "project",
            "entity_id": p.id,
            "route": f"/projects/{p.id}",
            "message": f"Projecto criado: {p.name}",
        }
    if h in ("nota", "note"):
        if not rest:
            return {"kind": "error", "message": "Indique o título da nota."}
        n = note_service.create_note(db, schemas.NoteCreate(title=rest))
        return {
            "kind": "created",
            "entity_type": "note",
            "entity_id": n.id,
            "route": f"/notes/{n.id}",
            "message": f"Nota criada: {n.title}",
        }
    if h in ("pesquisar", "procurar", "search", "?") or text.startswith("?"):
        q = rest if not text.startswith("?") else text[1:].strip()
        return {"kind": "search", "query": q, "hits": search(db, q, limit=10), "message": f"Resultados para «{q}»"}
    if h == "ir" or h in ("abrir", "open"):
        target = _norm(rest.removeprefix("para ").strip())
        route = ROUTES.get(target)
        if route:
            return {"kind": "navigate", "route": route, "message": f"A abrir {rest.removeprefix('para ')}"}
        return {"kind": "error", "message": f"Página desconhecida: {rest}"}
    if h == "foco":
        if _norm(rest) in ("iniciar", "comecar", "start"):
            s = task_service.start_focus(db, schemas.FocusStart())
            return {"kind": "result", "message": "Sessão de foco iniciada.", "data": {"id": s.id}}
        if _norm(rest) in ("parar", "terminar", "stop"):
            s = task_service.stop_focus(db)
            return {"kind": "result", "message": f"Sessão de foco registada: {s.duration_seconds // 60} min."}
        return {"kind": "error", "message": "Use «foco iniciar» ou «foco parar»."}
    if h in ("concluir", "done", "feito"):
        if not rest:
            return {"kind": "error", "message": "Indique parte do título da tarefa."}
        matches = list(
            db.scalars(
                select(Task)
                .where(Task.status != "done", Task.archived_at.is_(None), Task.title.ilike(f"%{rest}%"))
                .limit(5)
            )
        )
        if len(matches) != 1:
            return {
                "kind": "ambiguous" if matches else "error",
                "message": f"{len(matches)} tarefas correspondem; seja mais específico."
                if matches
                else "Nenhuma tarefa em aberto corresponde.",
                "hits": [{"entity_type": "task", "entity_id": t.id, "title": t.title} for t in matches],
            }
        t = task_service.change_status(db, matches[0].id, "done")
        return {
            "kind": "result",
            "entity_type": "task",
            "entity_id": t.id,
            "route": f"/tasks/{t.id}",
            "message": f"Tarefa concluída: {t.title}",
        }
    target = _norm(text)
    if target in ROUTES:
        return {"kind": "navigate", "route": ROUTES[target], "message": f"A abrir {text}"}
    return {
        "kind": "unknown",
        "message": "Comando não reconhecido. Experimente uma das sugestões.",
        "suggestions": SUGGESTIONS,
    }
