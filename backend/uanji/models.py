"""Modelo de dados (SQLAlchemy 2.x).

Convenções:
- Identificadores: UUID4 em texto (estáveis entre backups/exportações).
- Datas/horas: guardadas em UTC; devolvidas sempre com fuso (``UTCDateTime``).
- Arquivar (``archived_at``) é preferível a eliminar; eliminações são explícitas e
  propagam-se por ``ON DELETE CASCADE`` apenas para entidades dependentes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Dialect,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Guarda datetimes como UTC sem fuso no SQLite e devolve-os com tzinfo=UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Datetime sem fuso horário não é permitido")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- Projectos


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    # planned | active | paused | blocked | done | archived
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False, index=True)
    # low | medium | high | critical
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    objectives: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expected_results: Mapped[str] = mapped_column(Text, default="", nullable=False)
    blocked_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Milestone.position"
    )
    links: Mapped[list[ProjectLink]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectLink.created_at"
    )


class Milestone(TimestampMixin, Base):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped[Project] = relationship(back_populates="milestones")


class ProjectLink(TimestampMixin, Base):
    __tablename__ = "project_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # github | docs | link | other
    kind: Mapped[str] = mapped_column(String(20), default="link", nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)

    project: Mapped[Project] = relationship(back_populates="links")


# --------------------------------------------------------------------------- Tarefas


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # todo | in_progress | blocked | done
    status: Mapped[str] = mapped_column(String(20), default="todo", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    estimate_minutes: Mapped[int | None] = mapped_column(Integer)
    completion_criteria: Mapped[str] = mapped_column(Text, default="", nullable=False)
    blocked_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Quantas vezes o prazo foi adiado (para a revisão diária).
    postponed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Número curto e estável (#41) para referenciar a tarefa em commits, branches e PRs.
    number: Mapped[int | None] = mapped_column(Integer, index=True)
    # Centro de desempenho: início real do trabalho e tempo bloqueado acumulado.
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    blocked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    blocked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"), index=True)
    version_id: Mapped[str | None] = mapped_column(ForeignKey("project_versions.id", ondelete="SET NULL"), index=True)

    subtasks: Mapped[list[Task]] = relationship(cascade="all, delete-orphan", order_by="Task.position")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("task_id", "depends_on_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    depends_on_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


# --------------------------------------------------------------------------- Checklists


class Checklist(TimestampMixin, Base):
    __tablename__ = "checklists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # Identificador estável para os modelos incluídos de origem (evita duplicar no arranque).
    builtin_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    category: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    source_template_id: Mapped[str | None] = mapped_column(ForeignKey("checklists.id", ondelete="SET NULL"))

    items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="checklist", cascade="all, delete-orphan", order_by="ChecklistItem.position"
    )


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    checklist_id: Mapped[str] = mapped_column(ForeignKey("checklists.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    checklist: Mapped[Checklist] = relationship(back_populates="items")


# --------------------------------------------------------------------------- Notas e conhecimento

NOTE_KINDS = (
    "note",
    "decision",
    "idea",
    "concept",
    "solution",
    "error",
    "documentation",
    "reference",
    "lesson",
)


class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="note", nullable=False, index=True)
    # Itens visíveis na base de conhecimento.
    in_knowledge_base: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Incrementado a cada gravação; o cliente envia-o para detectar conflitos.
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class NoteRevision(Base):
    __tablename__ = "note_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    note_id: Mapped[str] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


ENTITY_TYPES = ("project", "task", "note", "event", "checklist", "automation")


class Relation(Base):
    """Relação explícita entre duas entidades (base do grafo de conhecimento)."""

    __tablename__ = "relations"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "target_type", "target_id", "label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(60), default="relacionado", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


# --------------------------------------------------------------------------- Agenda e revisões


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # event | work_block
    kind: Mapped[str] = mapped_column(String(20), default="event", nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)


class Review(TimestampMixin, Base):
    """Revisão diária ou semanal. ``period_start`` é o dia (diária) ou a segunda-feira (semanal)."""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("kind", "period_start"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # daily | weekly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    goals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    wins: Mapped[str] = mapped_column(Text, default="", nullable=False)
    blockers: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reflection: Mapped[str] = mapped_column(Text, default="", nullable=False)
    next_plan: Mapped[str] = mapped_column(Text, default="", nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# --------------------------------------------------------------------------- Automações


class Automation(TimestampMixin, Base):
    __tablename__ = "automations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False, index=True)
    # Gatilhos externos: hash do segredo do webhook e estado (ex.: último commit visto no GitHub).
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(64))
    trigger_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)

    versions: Mapped[list[AutomationVersion]] = relationship(
        cascade="all, delete-orphan", order_by="AutomationVersion.version"
    )


class AutomationVersion(Base):
    __tablename__ = "automation_versions"
    __table_args__ = (UniqueConstraint("automation_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    automation_id: Mapped[str] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    automation_id: Mapped[str] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    # Impede execuções duplicadas para o mesmo evento de origem.
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    # pending | running | success | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    steps: Mapped[list[AutomationRunStep]] = relationship(
        cascade="all, delete-orphan", order_by="AutomationRunStep.index"
    )


class AutomationRunStep(Base):
    __tablename__ = "automation_run_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("automation_runs.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    node_id: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    # success | failed | skipped | cancelled
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# --------------------------------------------------------------------------- Notificações


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # deadline | overdue | review | automation | backup | system
    category: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), default="info", nullable=False)  # info|warning|error
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # Chave que evita notificações repetidas para o mesmo facto.
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    native_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# --------------------------------------------------------------------------- Integrações e cofre


class Integration(TimestampMixin, Base):
    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    # Configuração não secreta (ex.: utilizador GitHub). Nunca tokens.
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    secret_id: Mapped[str | None] = mapped_column(ForeignKey("secrets.id", ondelete="SET NULL"))
    # not_configured | connected | error
    status: Mapped[str] = mapped_column(String(20), default="not_configured", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SecretEntry(TimestampMixin, Base):
    """Metadados de um segredo. O valor vive exclusivamente no macOS Keychain."""

    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    service: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Últimos 4 caracteres, para identificação visual. Nunca o valor completo.
    hint: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# --------------------------------------------------------------------------- Backups, histórico, definições


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # manual|automatic|pre_restore|pre_migration
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)  # ok|failed|missing
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- Assistente


class AssistantMessage(Base):
    """Histórico da conversa com o assistente (texto apenas; o áudio nunca é guardado).

    Retenção configurável em Definições → Voz e personalidade (``assistant.history_days``).
    """

    __tablename__ = "assistant_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    source: Mapped[str] = mapped_column(String(10), default="text", nullable=False)  # text | voice
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)


# --------------------------------------------------------------------------- Actividade no computador


class ActivitySession(Base):
    """Período contínuo numa aplicação (monitor de actividade opcional, só local).

    Não guarda conteúdo, teclas nem capturas de ecrã: apenas a aplicação em primeiro
    plano, o contexto conhecido (ex.: pasta aberta no VS Code) e, se autorizado, o título
    da janela. Períodos de inactividade não são registados.
    """

    __tablename__ = "activity_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    bundle_id: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="outros", nullable=False, index=True)
    context: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    ended_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# --------------------------------------------------------------------------- Objectivos, versões e código


class Goal(TimestampMixin, Base):
    """Objectivo mensurável: o progresso é a fracção das tarefas ligadas que está concluída."""

    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active | achieved | dropped


class ProjectVersion(TimestampMixin, Base):
    """Versão (release) de um projecto, ex.: v0.4. Agrupa tarefas e liga-se a uma tag Git."""

    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), default="planned", nullable=False
    )  # planned | in_progress | released
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    git_tag: Mapped[str] = mapped_column(String(100), default="", nullable=False)


class CodeLink(Base):
    """Alteração de código ligada a uma tarefa (commit, pull request, branch ou issue)."""

    __tablename__ = "code_links"
    __table_args__ = (UniqueConstraint("task_id", "kind", "repo", "ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # commit | pr | branch | issue
    repo: Mapped[str] = mapped_column(String(200), nullable=False)  # dono/repositório ou pasta local
    ref: Mapped[str] = mapped_column(String(200), nullable=False)  # sha, número ou nome do branch
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    author: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    happened_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
