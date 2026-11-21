"""Regras de negócio das tarefas, dependências e sessões de foco."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from .. import schemas
from ..errors import ConfirmationRequired, Conflict, ValidationFailed
from ..events import publish
from ..models import FocusSession, Project, Relation, Task, TaskDependency, utcnow
from .common import day_bounds, get_or_404, index_entity, local_today, log_activity, unindex_entity

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _index(db: Session, t: Task) -> None:
    index_entity(db, "task", t.id, t.title, "\n".join([t.description, t.notes, t.completion_criteria]))


def is_overdue(t: Task, now: datetime | None = None) -> bool:
    return t.status != "done" and t.due_at is not None and t.due_at < (now or utcnow())


def enrich(db: Session, tasks: list[Task]) -> list[schemas.TaskOut]:
    if not tasks:
        return []
    ids = [t.id for t in tasks]
    now = utcnow()
    sub = {
        r[0]: (r[1], int(r[2] or 0))
        for r in db.execute(
            select(Task.parent_id, func.count(Task.id), func.sum(func.iif(Task.status == "done", 1, 0)))
            .where(Task.parent_id.in_(ids), Task.archived_at.is_(None))
            .group_by(Task.parent_id)
        ).all()
    }
    deps: dict[str, list[str]] = {}
    open_deps: dict[str, int] = {}
    for task_id, dep_id, dep_status in db.execute(
        select(TaskDependency.task_id, TaskDependency.depends_on_id, Task.status)
        .join(Task, Task.id == TaskDependency.depends_on_id)
        .where(TaskDependency.task_id.in_(ids))
    ).all():
        deps.setdefault(task_id, []).append(dep_id)
        if dep_status != "done":
            open_deps[task_id] = open_deps.get(task_id, 0) + 1
    pids = {t.project_id for t in tasks if t.project_id}
    names = dict(db.execute(select(Project.id, Project.name).where(Project.id.in_(pids))).all()) if pids else {}
    out = []
    for t in tasks:
        o = schemas.TaskOut.model_validate(t)
        o.overdue = is_overdue(t, now)
        o.subtasks_total, o.subtasks_done = sub.get(t.id, (0, 0))
        o.project_name = names.get(t.project_id) if t.project_id else None
        o.depends_on = deps.get(t.id, [])
        o.blocked_by_open = open_deps.get(t.id, 0)
        out.append(o)
    return out


def list_tasks(
    db: Session,
    *,
    project_id: str | None = None,
    status: list[str] | None = None,
    priority: list[str] | None = None,
    q: str | None = None,
    due: str | None = None,  # overdue | today | week | none
    parent_id: str | None = None,
    top_level_only: bool = True,
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> schemas.Page[schemas.TaskOut]:
    stmt = select(Task)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if parent_id:
        stmt = stmt.where(Task.parent_id == parent_id)
    elif top_level_only:
        stmt = stmt.where(Task.parent_id.is_(None))
    if status:
        stmt = stmt.where(Task.status.in_(status))
    if priority:
        stmt = stmt.where(Task.priority.in_(priority))
    if not include_archived:
        stmt = stmt.where(Task.archived_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Task.title.ilike(like), Task.description.ilike(like)))
    now = utcnow()
    if due == "overdue":
        stmt = stmt.where(Task.status != "done", Task.due_at < now)
    elif due == "today":
        start, end = day_bounds(db, local_today(db))
        stmt = stmt.where(Task.due_at >= start, Task.due_at < end)
    elif due == "week":
        stmt = stmt.where(Task.due_at < now + timedelta(days=7), Task.due_at.is_not(None))
    elif due == "none":
        stmt = stmt.where(Task.due_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    prio = func.iif(
        Task.priority == "critical", 0, func.iif(Task.priority == "high", 1, func.iif(Task.priority == "medium", 2, 3))
    )
    rows = db.scalars(
        stmt.order_by(
            func.iif(Task.status == "done", 1, 0),
            func.iif(Task.due_at.is_(None), 1, 0),
            Task.due_at,
            prio,
            Task.position,
            Task.created_at,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.Page(items=enrich(db, list(rows)), total=total, limit=limit, offset=offset)


def get_detail(db: Session, task_id: str) -> schemas.TaskDetail:
    t = get_or_404(db, Task, task_id)
    base = enrich(db, [t])[0]
    subs = db.scalars(
        select(Task).where(Task.parent_id == t.id, Task.archived_at.is_(None)).order_by(Task.position)
    ).all()
    return schemas.TaskDetail(**base.model_dump(), subtasks=enrich(db, list(subs)))


def _check_refs(db: Session, project_id: str | None, parent_id: str | None) -> None:
    if project_id:
        get_or_404(db, Project, project_id)
    if parent_id:
        parent = get_or_404(db, Task, parent_id)
        if parent.parent_id is not None:
            raise ValidationFailed("Apenas é suportado um nível de subtarefas.")


def _check_links(db: Session, goal_id: str | None, version_id: str | None) -> None:
    from ..models import Goal, ProjectVersion

    if goal_id:
        get_or_404(db, Goal, goal_id)
    if version_id:
        get_or_404(db, ProjectVersion, version_id)


def create_task(db: Session, data: schemas.TaskCreate) -> Task:
    _check_refs(db, data.project_id, data.parent_id)
    _check_links(db, data.goal_id, data.version_id)
    if data.status == "blocked" and not data.blocked_reason:
        raise ValidationFailed("Indique o motivo do bloqueio.", {"field": "blocked_reason"})
    values = data.model_dump()
    if data.parent_id and not data.project_id:
        values["project_id"] = get_or_404(db, Task, data.parent_id).project_id
    t = Task(**values)
    t.position = (
        db.scalar(
            select(func.coalesce(func.max(Task.position), -1)).where(
                Task.parent_id.is_(None) if t.parent_id is None else Task.parent_id == t.parent_id
            )
        )
        or 0
    ) + 1
    t.number = (db.scalar(select(func.max(Task.number))) or 0) + 1
    now = utcnow()
    if t.status in ("in_progress", "done"):
        t.started_at = now
    if t.status == "blocked":
        t.blocked_at = now
    if t.status == "done":
        t.completed_at = now
    db.add(t)
    db.flush()
    _index(db, t)
    log_activity(db, "task", t.id, "created", f"Tarefa criada: {t.title}", {"project_id": t.project_id})
    return t


def update_task(db: Session, task_id: str, data: schemas.TaskUpdate) -> Task:
    t = get_or_404(db, Task, task_id)
    changes = data.model_dump(exclude_unset=True)
    if "project_id" in changes:
        _check_refs(db, changes["project_id"], None)
    _check_links(db, changes.get("goal_id"), changes.get("version_id"))
    new_status = changes.pop("status", None)
    if "due_at" in changes and t.due_at and changes["due_at"] and changes["due_at"] > t.due_at:
        t.postponed_count += 1
        log_activity(
            db,
            "task",
            t.id,
            "postponed",
            f"Prazo adiado: {t.title}",
            {"from": t.due_at.isoformat(), "to": changes["due_at"].isoformat()},
        )
    for k, v in changes.items():
        setattr(t, k, v)
    if new_status and new_status != t.status:
        set_status(db, t, new_status)
    db.flush()
    _index(db, t)
    if changes:
        log_activity(db, "task", t.id, "updated", f"Tarefa actualizada: {t.title}", {"fields": sorted(changes)})
    return t


def set_status(db: Session, t: Task, status: str) -> Task:
    if status == t.status:
        return t
    if status == "blocked" and not t.blocked_reason:
        raise ValidationFailed("Indique o motivo do bloqueio.", {"field": "blocked_reason"})
    if status == "done":
        open_deps = db.scalar(
            select(func.count(TaskDependency.id))
            .join(Task, Task.id == TaskDependency.depends_on_id)
            .where(TaskDependency.task_id == t.id, Task.status != "done")
        )
        if open_deps:
            raise ValidationFailed(f"Existem {open_deps} dependência(s) por concluir.")
        open_subs = db.scalar(
            select(func.count(Task.id)).where(Task.parent_id == t.id, Task.status != "done", Task.archived_at.is_(None))
        )
        if open_subs:
            raise ValidationFailed(f"Conclua primeiro as {open_subs} subtarefa(s) em aberto.")
    previous = t.status
    t.status = status
    now = utcnow()
    # Centro de desempenho: início real e tempo bloqueado acumulado.
    if status in ("in_progress", "done") and t.started_at is None:
        t.started_at = now
    if previous == "blocked" and t.blocked_at is not None:
        t.blocked_seconds += max(0, int((now - t.blocked_at).total_seconds()))
        t.blocked_at = None
    if status == "blocked":
        t.blocked_at = now
    if status == "done":
        t.completed_at = utcnow()
        log_activity(db, "task", t.id, "completed", f"Tarefa concluída: {t.title}", {"project_id": t.project_id})
        db.flush()
        publish(
            db,
            "task.completed",
            {
                "task_id": t.id,
                "title": t.title,
                "project_id": t.project_id,
                "completed_at": t.completed_at.isoformat(),
                "_depth": db.info.get("automation_depth", 0),
            },
        )
    else:
        if previous == "done":
            t.completed_at = None
            log_activity(db, "task", t.id, "reopened", f"Tarefa reaberta: {t.title}")
        else:
            log_activity(db, "task", t.id, "status", f"«{t.title}»: {previous} → {status}")
    return t


def change_status(db: Session, task_id: str, status: str, blocked_reason: str | None = None) -> Task:
    t = get_or_404(db, Task, task_id)
    if blocked_reason is not None:
        t.blocked_reason = blocked_reason
    return set_status(db, t, status)


def archive_task(db: Session, task_id: str, archived: bool) -> Task:
    t = get_or_404(db, Task, task_id)
    t.archived_at = utcnow() if archived else None
    log_activity(
        db,
        "task",
        t.id,
        "archived" if archived else "unarchived",
        f"Tarefa {'arquivada' if archived else 'desarquivada'}: {t.title}",
    )
    return t


def delete_task(db: Session, task_id: str, confirm: bool) -> None:
    t = get_or_404(db, Task, task_id)
    if not confirm:
        raise ConfirmationRequired("Eliminar a tarefa (e subtarefas) é irreversível. Confirme a operação.")
    ids = [t.id, *db.scalars(select(Task.id).where(Task.parent_id == t.id))]
    db.execute(
        delete(Relation).where(
            or_(
                and_(Relation.source_type == "task", Relation.source_id.in_(ids)),
                and_(Relation.target_type == "task", Relation.target_id.in_(ids)),
            )
        )
    )
    for i in ids:
        unindex_entity(db, "task", i)
    title = t.title
    db.delete(t)
    log_activity(db, "task", task_id, "deleted", f"Tarefa eliminada: {title}")


# --------------------------------------------------------------------------- Dependências


def _reachable(db: Session, start: str, target: str) -> bool:
    """True se ``target`` é alcançável a partir de ``start`` seguindo dependências."""
    seen, frontier = {start}, [start]
    while frontier:
        nxt = list(db.scalars(select(TaskDependency.depends_on_id).where(TaskDependency.task_id.in_(frontier))))
        if target in nxt:
            return True
        frontier = [n for n in nxt if n not in seen]
        seen.update(frontier)
    return False


def add_dependency(db: Session, task_id: str, depends_on_id: str) -> None:
    if task_id == depends_on_id:
        raise ValidationFailed("Uma tarefa não pode depender de si própria.")
    t = get_or_404(db, Task, task_id)
    d = get_or_404(db, Task, depends_on_id)
    if _reachable(db, depends_on_id, task_id):
        raise ValidationFailed("Esta dependência criaria um ciclo.")
    exists = db.scalar(
        select(TaskDependency.id).where(TaskDependency.task_id == t.id, TaskDependency.depends_on_id == d.id)
    )
    if exists:
        raise Conflict("Dependência já existe.")
    db.add(TaskDependency(task_id=t.id, depends_on_id=d.id))
    log_activity(db, "task", t.id, "dependency_added", f"«{t.title}» depende de «{d.title}»")


def remove_dependency(db: Session, task_id: str, depends_on_id: str) -> None:
    db.execute(
        delete(TaskDependency).where(TaskDependency.task_id == task_id, TaskDependency.depends_on_id == depends_on_id)
    )


# --------------------------------------------------------------------------- Foco


def active_focus(db: Session) -> FocusSession | None:
    return db.scalars(select(FocusSession).where(FocusSession.ended_at.is_(None))).first()


def start_focus(db: Session, data: schemas.FocusStart) -> FocusSession:
    if active_focus(db):
        raise Conflict("Já existe uma sessão de foco em curso.")
    project_id = data.project_id
    if data.task_id:
        task = get_or_404(db, Task, data.task_id)
        project_id = project_id or task.project_id
    s = FocusSession(task_id=data.task_id, project_id=project_id, started_at=utcnow(), note=data.note)
    db.add(s)
    db.flush()
    return s


def stop_focus(db: Session) -> FocusSession:
    s = active_focus(db)
    if s is None:
        raise Conflict("Não existe sessão de foco em curso.")
    s.ended_at = utcnow()
    s.duration_seconds = max(0, int((s.ended_at - s.started_at).total_seconds()))
    log_activity(
        db,
        "task" if s.task_id else "project",
        s.task_id or s.project_id or s.id,
        "focus",
        f"Sessão de foco registada: {s.duration_seconds // 60} min",
    )
    return s


def log_focus(db: Session, data: schemas.FocusLog) -> FocusSession:
    if data.started_at.tzinfo is None:
        raise ValidationFailed("A data deve incluir fuso horário.")
    project_id = data.project_id
    if data.task_id:
        project_id = project_id or get_or_404(db, Task, data.task_id).project_id
    s = FocusSession(
        task_id=data.task_id,
        project_id=project_id,
        started_at=data.started_at,
        ended_at=data.started_at + timedelta(minutes=data.minutes),
        duration_seconds=data.minutes * 60,
        note=data.note,
    )
    db.add(s)
    db.flush()
    return s
