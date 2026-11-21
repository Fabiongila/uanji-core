"""Rotas de checklists/modelos, notas, conhecimento, agenda e revisões."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import schemas
from ..services import agenda as asvc
from ..services import checklists as csvc
from ..services import notes as nsvc
from ..services import projects as psvc
from .deps import DB

router = APIRouter()


class ArchiveBody(BaseModel):
    archived: bool = True


class DuplicateBody(BaseModel):
    as_template: bool = False
    project_id: str | None = None
    task_id: str | None = None
    title: str | None = None


# --------------------------------------------------------------------------- Checklists


@router.get("/checklists", response_model=list[schemas.ChecklistOut], tags=["checklists"])
def list_checklists(
    db: DB, is_template: bool | None = None, project_id: str | None = None, task_id: str | None = None
) -> list[schemas.ChecklistOut]:
    return csvc.list_checklists(db, is_template, project_id, task_id)


@router.post("/checklists", response_model=schemas.ChecklistOut, status_code=201, tags=["checklists"])
def create_checklist(db: DB, body: schemas.ChecklistCreate) -> schemas.ChecklistOut:
    c = csvc.create_checklist(db, body)
    return csvc.get_checklist(db, c.id)


@router.get("/checklists/{checklist_id}", response_model=schemas.ChecklistOut, tags=["checklists"])
def get_checklist(db: DB, checklist_id: str) -> schemas.ChecklistOut:
    return csvc.get_checklist(db, checklist_id)


@router.patch("/checklists/{checklist_id}", response_model=schemas.ChecklistOut, tags=["checklists"])
def update_checklist(db: DB, checklist_id: str, body: schemas.ChecklistUpdate) -> schemas.ChecklistOut:
    csvc.update_checklist(db, checklist_id, body)
    return csvc.get_checklist(db, checklist_id)


@router.delete("/checklists/{checklist_id}", status_code=204, tags=["checklists"])
def delete_checklist(db: DB, checklist_id: str, confirm: bool = False) -> None:
    csvc.delete_checklist(db, checklist_id, confirm)


@router.post(
    "/checklists/{checklist_id}/items", response_model=schemas.ChecklistOut, status_code=201, tags=["checklists"]
)
def add_item(db: DB, checklist_id: str, body: schemas.ChecklistItemIn) -> schemas.ChecklistOut:
    csvc.add_item(db, checklist_id, body)
    db.expire_all()
    return csvc.get_checklist(db, checklist_id)


@router.patch("/checklist-items/{item_id}", response_model=schemas.ChecklistItemOut, tags=["checklists"])
def update_item(db: DB, item_id: str, body: schemas.ChecklistItemUpdate) -> schemas.ChecklistItemOut:
    return schemas.ChecklistItemOut.model_validate(csvc.update_item(db, item_id, body))


@router.delete("/checklist-items/{item_id}", status_code=204, tags=["checklists"])
def delete_item(db: DB, item_id: str) -> None:
    csvc.delete_item(db, item_id)


@router.post(
    "/checklists/{checklist_id}/duplicate", response_model=schemas.ChecklistOut, status_code=201, tags=["checklists"]
)
def duplicate(db: DB, checklist_id: str, body: DuplicateBody) -> schemas.ChecklistOut:
    c = csvc.duplicate(
        db,
        checklist_id,
        as_template=body.as_template,
        project_id=body.project_id,
        task_id=body.task_id,
        title=body.title,
    )
    return csvc.get_checklist(db, c.id)


@router.post("/projects/from-template", response_model=schemas.ProjectDetail, status_code=201, tags=["checklists"])
def project_from_template(db: DB, body: schemas.ProjectFromTemplate) -> schemas.ProjectDetail:
    p = csvc.project_from_template(db, body)
    db.flush()
    return psvc.get_detail(db, p.id)


# --------------------------------------------------------------------------- Notas


@router.get("/notes", response_model=schemas.Page[schemas.NoteSummary], tags=["notes"])
def list_notes(
    db: DB,
    q: str | None = None,
    kind: schemas.NoteKind | None = None,
    knowledge: bool | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    tag: str | None = None,
    include_archived: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> schemas.Page[schemas.NoteSummary]:
    return nsvc.list_notes(
        db,
        q=q,
        kind=kind,
        knowledge=knowledge,
        project_id=project_id,
        task_id=task_id,
        tag=tag,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )


@router.post("/notes", response_model=schemas.NoteOut, status_code=201, tags=["notes"])
def create_note(db: DB, body: schemas.NoteCreate) -> schemas.NoteOut:
    return schemas.NoteOut.model_validate(nsvc.create_note(db, body))


@router.get("/notes/{note_id}", response_model=schemas.NoteOut, tags=["notes"])
def get_note(db: DB, note_id: str) -> schemas.NoteOut:
    from ..models import Note
    from ..services.common import get_or_404

    return schemas.NoteOut.model_validate(get_or_404(db, Note, note_id))


@router.patch("/notes/{note_id}", response_model=schemas.NoteOut, tags=["notes"])
def update_note(db: DB, note_id: str, body: schemas.NoteUpdate) -> schemas.NoteOut:
    return schemas.NoteOut.model_validate(nsvc.update_note(db, note_id, body))


@router.post("/notes/{note_id}/archive", response_model=schemas.NoteOut, tags=["notes"])
def archive_note(db: DB, note_id: str, body: ArchiveBody) -> schemas.NoteOut:
    return schemas.NoteOut.model_validate(nsvc.archive_note(db, note_id, body.archived))


@router.delete("/notes/{note_id}", status_code=204, tags=["notes"])
def delete_note(db: DB, note_id: str, confirm: bool = False) -> None:
    nsvc.delete_note(db, note_id, confirm)


@router.get("/notes/{note_id}/revisions", response_model=list[schemas.NoteRevisionOut], tags=["notes"])
def note_revisions(db: DB, note_id: str) -> list[schemas.NoteRevisionOut]:
    return [schemas.NoteRevisionOut.model_validate(r) for r in nsvc.revisions(db, note_id)]


@router.post("/notes/{note_id}/revisions/{revision_id}/restore", response_model=schemas.NoteOut, tags=["notes"])
def restore_revision(db: DB, note_id: str, revision_id: str) -> schemas.NoteOut:
    return schemas.NoteOut.model_validate(nsvc.restore_revision(db, note_id, revision_id))


# --------------------------------------------------------------------------- Relações / conhecimento


@router.post("/relations", response_model=schemas.RelationOut, status_code=201, tags=["knowledge"])
def add_relation(db: DB, body: schemas.RelationIn) -> schemas.RelationOut:
    return schemas.RelationOut.model_validate(nsvc.add_relation(db, body))


@router.delete("/relations/{relation_id}", status_code=204, tags=["knowledge"])
def delete_relation(db: DB, relation_id: str) -> None:
    nsvc.delete_relation(db, relation_id)


@router.get("/relations", tags=["knowledge"])
def relations_for(db: DB, entity_type: schemas.EntityType, entity_id: str) -> list[dict[str, Any]]:
    return nsvc.relations_for(db, entity_type, entity_id)


@router.get("/knowledge/graph", response_model=schemas.Graph, tags=["knowledge"])
def knowledge_graph(db: DB, include_tasks: bool = False) -> schemas.Graph:
    return nsvc.knowledge_graph(db, include_tasks=include_tasks)


# --------------------------------------------------------------------------- Agenda


@router.get("/agenda", tags=["agenda"])
def agenda(db: DB, start: date, days: int = Query(7, ge=1, le=42)) -> dict[str, Any]:
    return asvc.agenda(db, start, days)


@router.get("/events", response_model=list[schemas.EventOut], tags=["agenda"])
def list_events(db: DB, start: datetime, end: datetime) -> list[schemas.EventOut]:
    return [schemas.EventOut.model_validate(e) for e in asvc.list_events(db, start, end)]


@router.post("/events", response_model=schemas.EventOut, status_code=201, tags=["agenda"])
def create_event(db: DB, body: schemas.EventCreate) -> schemas.EventOut:
    return schemas.EventOut.model_validate(asvc.create_event(db, body))


@router.patch("/events/{event_id}", response_model=schemas.EventOut, tags=["agenda"])
def update_event(db: DB, event_id: str, body: schemas.EventUpdate) -> schemas.EventOut:
    return schemas.EventOut.model_validate(asvc.update_event(db, event_id, body))


@router.delete("/events/{event_id}", status_code=204, tags=["agenda"])
def delete_event(db: DB, event_id: str, confirm: bool = False) -> None:
    asvc.delete_event(db, event_id, confirm)


@router.get("/reviews/{kind}", response_model=schemas.ReviewContext, tags=["reviews"])
def get_review(db: DB, kind: Literal["daily", "weekly"], day: date | None = None) -> schemas.ReviewContext:
    return asvc.review_context(db, kind, day)


@router.put("/reviews/{kind}/{day}", response_model=schemas.ReviewOut, tags=["reviews"])
def update_review(db: DB, kind: Literal["daily", "weekly"], day: date, body: schemas.ReviewUpdate) -> schemas.ReviewOut:
    return schemas.ReviewOut.model_validate(asvc.update_review(db, kind, day, body))
