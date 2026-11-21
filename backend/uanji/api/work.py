"""Rotas de projectos, tarefas e sessões de foco."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from .. import schemas
from ..services import projects as svc
from ..services import tasks as tsvc
from .deps import DB

router = APIRouter()


class ArchiveBody(BaseModel):
    archived: bool = True


class StatusBody(BaseModel):
    status: schemas.TaskStatus
    blocked_reason: str | None = Field(default=None, max_length=5000)


# --------------------------------------------------------------------------- Projectos


@router.get("/projects", response_model=schemas.Page[schemas.ProjectOut], tags=["projects"])
def list_projects(
    db: DB,
    status: schemas.ProjectStatus | None = None,
    q: str | None = None,
    include_archived: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.ProjectOut]:
    return svc.list_projects(db, status=status, q=q, include_archived=include_archived, limit=limit, offset=offset)


@router.post("/projects", response_model=schemas.ProjectDetail, status_code=201, tags=["projects"])
def create_project(db: DB, body: schemas.ProjectCreate) -> schemas.ProjectDetail:
    p = svc.create_project(db, body)
    db.flush()
    return svc.get_detail(db, p.id)


@router.get("/projects/{project_id}", response_model=schemas.ProjectDetail, tags=["projects"])
def get_project(db: DB, project_id: str) -> schemas.ProjectDetail:
    return svc.get_detail(db, project_id)


@router.patch("/projects/{project_id}", response_model=schemas.ProjectDetail, tags=["projects"])
def update_project(db: DB, project_id: str, body: schemas.ProjectUpdate) -> schemas.ProjectDetail:
    svc.update_project(db, project_id, body)
    db.flush()
    return svc.get_detail(db, project_id)


@router.post("/projects/{project_id}/archive", response_model=schemas.ProjectDetail, tags=["projects"])
def archive_project(db: DB, project_id: str, body: ArchiveBody) -> schemas.ProjectDetail:
    svc.archive_project(db, project_id, body.archived)
    db.flush()
    return svc.get_detail(db, project_id)


@router.delete("/projects/{project_id}", status_code=204, tags=["projects"])
def delete_project(db: DB, project_id: str, confirm: bool = False) -> None:
    svc.delete_project(db, project_id, confirm)


@router.get("/projects/{project_id}/history", response_model=list[schemas.ActivityOut], tags=["projects"])
def project_history(db: DB, project_id: str) -> list[schemas.ActivityOut]:
    return [schemas.ActivityOut.model_validate(a) for a in svc.history(db, project_id)]


@router.post(
    "/projects/{project_id}/milestones", response_model=schemas.MilestoneOut, status_code=201, tags=["projects"]
)
def add_milestone(db: DB, project_id: str, body: schemas.MilestoneIn) -> schemas.MilestoneOut:
    m = svc.add_milestone(db, project_id, body)
    db.flush()
    return schemas.MilestoneOut.model_validate(m)


@router.put("/milestones/{milestone_id}", response_model=schemas.MilestoneOut, tags=["projects"])
def update_milestone(db: DB, milestone_id: str, body: schemas.MilestoneIn) -> schemas.MilestoneOut:
    m = svc.update_milestone(db, milestone_id, body)
    db.flush()
    return schemas.MilestoneOut.model_validate(m)


@router.delete("/milestones/{milestone_id}", status_code=204, tags=["projects"])
def delete_milestone(db: DB, milestone_id: str) -> None:
    svc.delete_milestone(db, milestone_id)


@router.post("/projects/{project_id}/links", response_model=schemas.ProjectLinkOut, status_code=201, tags=["projects"])
def add_link(db: DB, project_id: str, body: schemas.ProjectLinkIn) -> schemas.ProjectLinkOut:
    link = svc.add_link(db, project_id, body)
    db.flush()
    return schemas.ProjectLinkOut.model_validate(link)


@router.delete("/links/{link_id}", status_code=204, tags=["projects"])
def delete_link(db: DB, link_id: str) -> None:
    svc.delete_link(db, link_id)


# --------------------------------------------------------------------------- Tarefas


@router.get("/tasks", response_model=schemas.Page[schemas.TaskOut], tags=["tasks"])
def list_tasks(
    db: DB,
    project_id: str | None = None,
    status: list[schemas.TaskStatus] | None = Query(None),
    priority: list[schemas.Priority] | None = Query(None),
    q: str | None = None,
    due: Literal["overdue", "today", "week", "none"] | None = None,
    parent_id: str | None = None,
    include_subtasks: bool = False,
    include_archived: bool = False,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.TaskOut]:
    return tsvc.list_tasks(
        db,
        project_id=project_id,
        status=list(status) if status else None,
        priority=list(priority) if priority else None,
        q=q,
        due=due,
        parent_id=parent_id,
        top_level_only=not include_subtasks,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.post("/tasks", response_model=schemas.TaskDetail, status_code=201, tags=["tasks"])
def create_task(db: DB, body: schemas.TaskCreate) -> schemas.TaskDetail:
    t = tsvc.create_task(db, body)
    return tsvc.get_detail(db, t.id)


@router.get("/tasks/{task_id}", response_model=schemas.TaskDetail, tags=["tasks"])
def get_task(db: DB, task_id: str) -> schemas.TaskDetail:
    return tsvc.get_detail(db, task_id)


@router.patch("/tasks/{task_id}", response_model=schemas.TaskDetail, tags=["tasks"])
def update_task(db: DB, task_id: str, body: schemas.TaskUpdate) -> schemas.TaskDetail:
    tsvc.update_task(db, task_id, body)
    return tsvc.get_detail(db, task_id)


@router.post("/tasks/{task_id}/status", response_model=schemas.TaskDetail, tags=["tasks"])
def set_status(db: DB, task_id: str, body: StatusBody) -> schemas.TaskDetail:
    tsvc.change_status(db, task_id, body.status, body.blocked_reason)
    db.flush()
    return tsvc.get_detail(db, task_id)


@router.post("/tasks/{task_id}/archive", response_model=schemas.TaskDetail, tags=["tasks"])
def archive_task(db: DB, task_id: str, body: ArchiveBody) -> schemas.TaskDetail:
    tsvc.archive_task(db, task_id, body.archived)
    db.flush()
    return tsvc.get_detail(db, task_id)


@router.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
def delete_task(db: DB, task_id: str, confirm: bool = False) -> None:
    tsvc.delete_task(db, task_id, confirm)


@router.post("/tasks/{task_id}/dependencies", response_model=schemas.TaskDetail, tags=["tasks"])
def add_dependency(db: DB, task_id: str, body: schemas.DependencyIn) -> schemas.TaskDetail:
    tsvc.add_dependency(db, task_id, body.depends_on_id)
    db.flush()
    return tsvc.get_detail(db, task_id)


@router.delete("/tasks/{task_id}/dependencies/{depends_on_id}", response_model=schemas.TaskDetail, tags=["tasks"])
def remove_dependency(db: DB, task_id: str, depends_on_id: str) -> schemas.TaskDetail:
    tsvc.remove_dependency(db, task_id, depends_on_id)
    return tsvc.get_detail(db, task_id)


# --------------------------------------------------------------------------- Foco


@router.get("/focus/active", response_model=schemas.FocusOut | None, tags=["focus"])
def focus_active(db: DB) -> schemas.FocusOut | None:
    s = tsvc.active_focus(db)
    return schemas.FocusOut.model_validate(s) if s else None


@router.post("/focus/start", response_model=schemas.FocusOut, status_code=201, tags=["focus"])
def focus_start(db: DB, body: schemas.FocusStart) -> schemas.FocusOut:
    return schemas.FocusOut.model_validate(tsvc.start_focus(db, body))


@router.post("/focus/stop", response_model=schemas.FocusOut, tags=["focus"])
def focus_stop(db: DB) -> schemas.FocusOut:
    return schemas.FocusOut.model_validate(tsvc.stop_focus(db))


@router.post("/focus/log", response_model=schemas.FocusOut, status_code=201, tags=["focus"])
def focus_log(db: DB, body: schemas.FocusLog) -> schemas.FocusOut:
    return schemas.FocusOut.model_validate(tsvc.log_focus(db, body))
