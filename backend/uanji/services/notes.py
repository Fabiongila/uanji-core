"""Notas Markdown, histórico de revisões, relações e grafo de conhecimento."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from .. import schemas
from ..errors import ConfirmationRequired, Conflict, ValidationFailed
from ..models import (
    Automation,
    Checklist,
    Event,
    Note,
    NoteRevision,
    Project,
    Relation,
    Task,
    utcnow,
)
from .common import get_or_404, index_entity, log_activity, unindex_entity

# Gravações automáticas consecutivas dentro desta janela partilham a mesma revisão
# histórica (evita uma revisão por cada tecla).
REVISION_WINDOW = timedelta(minutes=10)
MAX_REVISIONS = 50

ENTITY_MODELS: dict[str, type] = {
    "project": Project,
    "task": Task,
    "note": Note,
    "event": Event,
    "checklist": Checklist,
    "automation": Automation,
}


def _index(db: Session, n: Note) -> None:
    index_entity(db, "note", n.id, n.title, n.content + "\n" + " ".join(n.tags))


def _check_links(db: Session, project_id: str | None, task_id: str | None) -> None:
    if project_id:
        get_or_404(db, Project, project_id)
    if task_id:
        get_or_404(db, Task, task_id)


def summary(n: Note) -> schemas.NoteSummary:
    s = schemas.NoteSummary.model_validate(n)
    s.excerpt = " ".join(n.content.split())[:160]
    return s


def list_notes(
    db: Session,
    *,
    q: str | None = None,
    kind: str | None = None,
    knowledge: bool | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    tag: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> schemas.Page[schemas.NoteSummary]:
    stmt = select(Note)
    if not include_archived:
        stmt = stmt.where(Note.archived_at.is_(None))
    if kind:
        stmt = stmt.where(Note.kind == kind)
    if knowledge is not None:
        stmt = stmt.where(Note.in_knowledge_base == knowledge)
    if project_id:
        stmt = stmt.where(Note.project_id == project_id)
    if task_id:
        stmt = stmt.where(Note.task_id == task_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Note.title.ilike(like), Note.content.ilike(like)))
    rows = list(db.scalars(stmt.order_by(Note.pinned.desc(), Note.updated_at.desc())))
    if tag:
        rows = [n for n in rows if tag.lower() in n.tags]
    total = len(rows)
    page = rows[offset : offset + limit]
    return schemas.Page(items=[summary(n) for n in page], total=total, limit=limit, offset=offset)


def create_note(db: Session, data: schemas.NoteCreate) -> Note:
    _check_links(db, data.project_id, data.task_id)
    n = Note(**data.model_dump())
    db.add(n)
    db.flush()
    db.add(NoteRevision(note_id=n.id, revision=1, title=n.title, content=n.content))
    _index(db, n)
    log_activity(db, "note", n.id, "created", f"Nota criada: {n.title}", {"project_id": n.project_id})
    return n


def update_note(db: Session, note_id: str, data: schemas.NoteUpdate) -> Note:
    n = get_or_404(db, Note, note_id)
    changes = data.model_dump(exclude_unset=True)
    base = changes.pop("base_revision", None)
    if base is not None and base != n.revision:
        raise Conflict(
            "A nota foi alterada noutro local. Recarregue antes de gravar.",
            {"current_revision": n.revision},
        )
    if "tags" in changes and changes["tags"] is not None:
        changes["tags"] = schemas.NoteCreate(title="x", tags=changes["tags"]).tags
    _check_links(db, changes.get("project_id"), changes.get("task_id"))
    content_changed = any(k in changes and changes[k] != getattr(n, k) for k in ("title", "content"))
    for k, v in changes.items():
        setattr(n, k, v)
    if content_changed:
        n.revision += 1
        last = db.scalars(
            select(NoteRevision).where(NoteRevision.note_id == n.id).order_by(NoteRevision.revision.desc())
        ).first()
        if last and utcnow() - last.created_at < REVISION_WINDOW and last.revision > 1:
            last.title, last.content, last.revision = n.title, n.content, n.revision
        else:
            db.add(NoteRevision(note_id=n.id, revision=n.revision, title=n.title, content=n.content))
            _prune_revisions(db, n.id)
    db.flush()
    _index(db, n)
    return n


def _prune_revisions(db: Session, note_id: str) -> None:
    ids = list(
        db.scalars(
            select(NoteRevision.id)
            .where(NoteRevision.note_id == note_id)
            .order_by(NoteRevision.revision.desc())
            .offset(MAX_REVISIONS)
        )
    )
    if ids:
        db.execute(delete(NoteRevision).where(NoteRevision.id.in_(ids)))


def revisions(db: Session, note_id: str) -> list[NoteRevision]:
    get_or_404(db, Note, note_id)
    return list(
        db.scalars(select(NoteRevision).where(NoteRevision.note_id == note_id).order_by(NoteRevision.revision.desc()))
    )


def restore_revision(db: Session, note_id: str, revision_id: str) -> Note:
    rev = get_or_404(db, NoteRevision, revision_id)
    if rev.note_id != note_id:
        raise ValidationFailed("A revisão não pertence a esta nota.")
    n = update_note(db, note_id, schemas.NoteUpdate(title=rev.title, content=rev.content))
    log_activity(db, "note", n.id, "restored", f"Nota restaurada para a revisão {rev.revision}: {n.title}")
    return n


def archive_note(db: Session, note_id: str, archived: bool) -> Note:
    n = get_or_404(db, Note, note_id)
    n.archived_at = utcnow() if archived else None
    log_activity(db, "note", n.id, "archived" if archived else "unarchived", f"Nota: {n.title}")
    return n


def delete_note(db: Session, note_id: str, confirm: bool) -> None:
    n = get_or_404(db, Note, note_id)
    if not confirm:
        raise ConfirmationRequired("Eliminar a nota e o seu histórico é irreversível. Confirme a operação.")
    _delete_relations_of(db, "note", n.id)
    unindex_entity(db, "note", n.id)
    log_activity(db, "note", n.id, "deleted", f"Nota eliminada: {n.title}")
    db.delete(n)


# --------------------------------------------------------------------------- Relações


def _delete_relations_of(db: Session, etype: str, eid: str) -> None:
    db.execute(
        delete(Relation).where(
            or_(
                and_(Relation.source_type == etype, Relation.source_id == eid),
                and_(Relation.target_type == etype, Relation.target_id == eid),
            )
        )
    )


def entity_label(db: Session, etype: str, eid: str) -> str | None:
    model = ENTITY_MODELS.get(etype)
    if model is None:
        return None
    obj = db.get(model, eid)
    if obj is None:
        return None
    return str(getattr(obj, "name", None) or getattr(obj, "title", ""))


def add_relation(db: Session, data: schemas.RelationIn) -> Relation:
    if (data.source_type, data.source_id) == (data.target_type, data.target_id):
        raise ValidationFailed("Não é possível relacionar um item consigo próprio.")
    for t, i in ((data.source_type, data.source_id), (data.target_type, data.target_id)):
        if entity_label(db, t, i) is None:
            raise ValidationFailed(f"Item inexistente: {t} {i}")
    exists = db.scalar(
        select(func.count(Relation.id)).where(
            Relation.source_type == data.source_type,
            Relation.source_id == data.source_id,
            Relation.target_type == data.target_type,
            Relation.target_id == data.target_id,
            Relation.label == data.label,
        )
    )
    if exists:
        raise Conflict("Relação já existe.")
    r = Relation(**data.model_dump())
    db.add(r)
    db.flush()
    return r


def delete_relation(db: Session, relation_id: str) -> None:
    db.delete(get_or_404(db, Relation, relation_id))


def relations_for(db: Session, etype: str, eid: str) -> list[dict[str, str]]:
    rows = db.scalars(
        select(Relation).where(
            or_(
                and_(Relation.source_type == etype, Relation.source_id == eid),
                and_(Relation.target_type == etype, Relation.target_id == eid),
            )
        )
    ).all()
    out = []
    for r in rows:
        outgoing = r.source_type == etype and r.source_id == eid
        other_t, other_i = (r.target_type, r.target_id) if outgoing else (r.source_type, r.source_id)
        out.append(
            {
                "id": r.id,
                "label": r.label,
                "direction": "out" if outgoing else "in",
                "entity_type": other_t,
                "entity_id": other_i,
                "title": entity_label(db, other_t, other_i) or "(removido)",
            }
        )
    return out


def knowledge_graph(db: Session, include_tasks: bool = False, limit: int = 300) -> schemas.Graph:
    """Grafo com notas da base de conhecimento, projectos associados e relações explícitas.

    As arestas ``implicit`` derivam das chaves estrangeiras (nota → projecto/tarefa).
    """
    nodes: dict[str, schemas.GraphNode] = {}
    edges: list[schemas.GraphEdge] = []

    def add_node(etype: str, eid: str, label: str, kind: str | None = None) -> str:
        key = f"{etype}:{eid}"
        if key not in nodes:
            nodes[key] = schemas.GraphNode(id=key, type=etype, entity_id=eid, label=label, kind=kind)
        return key

    notes = db.scalars(
        select(Note).where(Note.in_knowledge_base.is_(True), Note.archived_at.is_(None)).limit(limit)
    ).all()
    for n in notes:
        k = add_node("note", n.id, n.title, n.kind)
        if n.project_id:
            p = db.get(Project, n.project_id)
            if p:
                pk = add_node("project", p.id, p.name, p.status)
                edges.append(schemas.GraphEdge(id=f"fk-{n.id}-p", source=k, target=pk, label="projecto", implicit=True))
        if include_tasks and n.task_id:
            t = db.get(Task, n.task_id)
            if t:
                tk = add_node("task", t.id, t.title, t.status)
                edges.append(schemas.GraphEdge(id=f"fk-{n.id}-t", source=k, target=tk, label="tarefa", implicit=True))
    for r in db.scalars(select(Relation).limit(limit * 3)):
        if not include_tasks and "task" in (r.source_type, r.target_type):
            continue
        sl = entity_label(db, r.source_type, r.source_id)
        tl = entity_label(db, r.target_type, r.target_id)
        if sl is None or tl is None:
            continue
        src = add_node(r.source_type, r.source_id, sl)
        dst = add_node(r.target_type, r.target_id, tl)
        edges.append(schemas.GraphEdge(id=r.id, source=src, target=dst, label=r.label))
    return schemas.Graph(nodes=list(nodes.values()), edges=edges)
