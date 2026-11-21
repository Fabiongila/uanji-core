"""Regras de negócio dos projectos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..errors import ConfirmationRequired, ValidationFailed
from ..models import Activity, Milestone, Project, ProjectLink, Relation, Task, utcnow
from .common import get_or_404, index_entity, log_activity, unindex_entity

STALE_DAYS = 14


def _index(db: Session, p: Project) -> None:
    body = "\n".join([p.description, p.category, p.objectives, p.expected_results])
    index_entity(db, "project", p.id, p.name, body)


def progress_for(db: Session, project_ids: list[str]) -> dict[str, schemas.ProjectProgress]:
    """Regra documentada: % = tarefas de topo concluídas / tarefas de topo não arquivadas."""
    if not project_ids:
        return {}
    now = utcnow()
    task_rows = db.execute(
        select(
            Task.project_id,
            func.count(Task.id),
            func.sum(func.iif(Task.status == "done", 1, 0)),
            func.sum(func.iif(and_(Task.status != "done", Task.due_at < now), 1, 0)),
        )
        .where(Task.project_id.in_(project_ids), Task.parent_id.is_(None), Task.archived_at.is_(None))
        .group_by(Task.project_id)
    ).all()
    ms_rows = db.execute(
        select(
            Milestone.project_id,
            func.count(Milestone.id),
            func.sum(func.iif(Milestone.done_at.is_not(None), 1, 0)),
        )
        .where(Milestone.project_id.in_(project_ids))
        .group_by(Milestone.project_id)
    ).all()
    tasks = {r[0]: (r[1], int(r[2] or 0), int(r[3] or 0)) for r in task_rows}
    ms = {r[0]: (r[1], int(r[2] or 0)) for r in ms_rows}
    out = {}
    for pid in project_ids:
        total, done, overdue = tasks.get(pid, (0, 0, 0))
        mt, md = ms.get(pid, (0, 0))
        out[pid] = schemas.ProjectProgress(
            tasks_total=total,
            tasks_done=done,
            milestones_total=mt,
            milestones_done=md,
            percent=round(done * 100 / total) if total else None,
            overdue_tasks=overdue,
        )
    return out


def _last_activity(db: Session, project_ids: list[str]) -> dict[str, datetime]:
    if not project_ids:
        return {}
    direct = db.execute(
        select(Activity.entity_id, func.max(Activity.created_at))
        .where(Activity.entity_type == "project", Activity.entity_id.in_(project_ids))
        .group_by(Activity.entity_id)
    ).all()
    via_tasks = db.execute(
        select(Task.project_id, func.max(Task.updated_at))
        .where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    ).all()
    out: dict[str, datetime] = {}
    for pid, ts in [*direct, *via_tasks]:
        if pid is None or ts is None:
            continue
        # func.max em SQLite devolve texto/naive: o TypeDecorator não é aplicado.
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if pid not in out or ts > out[pid]:
            out[pid] = ts
    return out


def enrich(db: Session, projects: list[Project]) -> list[schemas.ProjectOut]:
    ids = [p.id for p in projects]
    prog = progress_for(db, ids)
    last = _last_activity(db, ids)
    threshold = utcnow() - timedelta(days=STALE_DAYS)
    out = []
    for p in projects:
        item = schemas.ProjectOut.model_validate(p)
        item.progress = prog.get(p.id)
        item.last_activity_at = last.get(p.id, p.updated_at)
        item.stale = p.status == "active" and item.last_activity_at < threshold
        out.append(item)
    return out


def list_projects(
    db: Session,
    status: str | None = None,
    q: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> schemas.Page[schemas.ProjectOut]:
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    elif not include_archived:
        stmt = stmt.where(Project.archived_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Project.name.ilike(like), Project.description.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(
            func.iif(Project.status == "active", 0, func.iif(Project.status == "blocked", 1, 2)),
            Project.updated_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return schemas.Page(items=enrich(db, list(rows)), total=total, limit=limit, offset=offset)


def get_detail(db: Session, project_id: str) -> schemas.ProjectDetail:
    p = db.scalars(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.milestones), selectinload(Project.links))
    ).first()
    if p is None:
        get_or_404(db, Project, project_id)
        raise AssertionError
    base = enrich(db, [p])[0]
    return schemas.ProjectDetail(
        **base.model_dump(),
        milestones=[schemas.MilestoneOut.model_validate(m) for m in p.milestones],
        links=[schemas.ProjectLinkOut.model_validate(link) for link in p.links],
    )


def create_project(db: Session, data: schemas.ProjectCreate) -> Project:
    p = Project(**data.model_dump())
    if p.status == "archived":
        p.archived_at = utcnow()
    db.add(p)
    db.flush()
    _index(db, p)
    log_activity(db, "project", p.id, "created", f"Projecto criado: {p.name}")
    return p


def update_project(db: Session, project_id: str, data: schemas.ProjectUpdate) -> Project:
    p = get_or_404(db, Project, project_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("status") == "blocked" and not (changes.get("blocked_reason") or p.blocked_reason):
        raise ValidationFailed("Indique o motivo do bloqueio.", {"field": "blocked_reason"})
    start = changes.get("start_date", p.start_date)
    due = changes.get("due_date", p.due_date)
    if start and due and due < start:
        raise ValidationFailed("A data de fim não pode ser anterior à data de início.")
    diff = {}
    for k, v in changes.items():
        old = getattr(p, k)
        if old != v:
            diff[k] = {"from": str(old) if old is not None else None, "to": str(v) if v is not None else None}
            setattr(p, k, v)
    if "status" in changes:
        p.archived_at = utcnow() if p.status == "archived" else None
    if diff:
        db.flush()
        _index(db, p)
        summary = f"Projecto actualizado: {p.name}"
        if "status" in diff:
            summary = f"Estado de «{p.name}»: {diff['status']['from']} → {diff['status']['to']}"
        log_activity(db, "project", p.id, "updated", summary, {"changes": diff})
    return p


def archive_project(db: Session, project_id: str, archived: bool) -> Project:
    p = get_or_404(db, Project, project_id)
    p.status = "archived" if archived else "paused"
    p.archived_at = utcnow() if archived else None
    log_activity(
        db,
        "project",
        p.id,
        "archived" if archived else "unarchived",
        f"«{p.name}» arquivado" if archived else f"«{p.name}» reactivado (em pausa)",
    )
    return p


def delete_project(db: Session, project_id: str, confirm: bool) -> None:
    p = get_or_404(db, Project, project_id)
    if not confirm:
        raise ConfirmationRequired(
            "Eliminar um projecto é irreversível. Confirme a operação.",
            {"tasks_detached": db.scalar(select(func.count(Task.id)).where(Task.project_id == p.id))},
        )
    name = p.name
    db.execute(
        delete(Relation).where(
            or_(
                and_(Relation.source_type == "project", Relation.source_id == p.id),
                and_(Relation.target_type == "project", Relation.target_id == p.id),
            )
        )
    )
    unindex_entity(db, "project", p.id)
    db.delete(p)
    log_activity(db, "project", project_id, "deleted", f"Projecto eliminado: {name}")


# --------------------------------------------------------------------------- Marcos e links


def add_milestone(db: Session, project_id: str, data: schemas.MilestoneIn) -> Milestone:
    p = get_or_404(db, Project, project_id)
    pos = db.scalar(select(func.coalesce(func.max(Milestone.position), -1)).where(Milestone.project_id == p.id)) or 0
    m = Milestone(
        project_id=p.id,
        title=data.title,
        due_date=data.due_date,
        done_at=utcnow() if data.done else None,
        position=pos + 1,
    )
    db.add(m)
    log_activity(db, "project", p.id, "milestone_added", f"Marco adicionado a «{p.name}»: {data.title}")
    return m


def update_milestone(db: Session, milestone_id: str, data: schemas.MilestoneIn) -> Milestone:
    m = get_or_404(db, Milestone, milestone_id)
    was_done = m.done_at is not None
    m.title = data.title
    m.due_date = data.due_date
    if data.done and not was_done:
        m.done_at = utcnow()
        log_activity(db, "project", m.project_id, "milestone_done", f"Marco concluído: {m.title}")
    elif not data.done:
        m.done_at = None
    return m


def delete_milestone(db: Session, milestone_id: str) -> None:
    m = get_or_404(db, Milestone, milestone_id)
    db.delete(m)


def add_link(db: Session, project_id: str, data: schemas.ProjectLinkIn) -> ProjectLink:
    p = get_or_404(db, Project, project_id)
    url = str(data.url)
    kind = data.kind
    if "github.com/" in url and kind == "link":
        kind = "github"
    link = ProjectLink(project_id=p.id, kind=kind, title=data.title or url, url=url)
    db.add(link)
    log_activity(db, "project", p.id, "link_added", f"Link adicionado a «{p.name}»: {link.title}")
    return link


def delete_link(db: Session, link_id: str) -> None:
    db.delete(get_or_404(db, ProjectLink, link_id))


def history(db: Session, project_id: str, limit: int = 100) -> list[Activity]:
    get_or_404(db, Project, project_id)
    task_ids = select(Task.id).where(Task.project_id == project_id)
    return list(
        db.scalars(
            select(Activity)
            .where(
                or_(
                    and_(Activity.entity_type == "project", Activity.entity_id == project_id),
                    and_(Activity.entity_type == "task", Activity.entity_id.in_(task_ids)),
                )
            )
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
    )
