"""Schemas Pydantic: contratos da API (entrada validada e saída consistente)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

ProjectStatus = Literal["planned", "active", "paused", "blocked", "done", "archived"]
Priority = Literal["low", "medium", "high", "critical"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
NoteKind = Literal["note", "decision", "idea", "concept", "solution", "error", "documentation", "reference", "lesson"]
EntityType = Literal["project", "task", "note", "event", "checklist", "automation"]
LinkKind = Literal["github", "docs", "link", "folder", "other"]

Name = Field(min_length=1, max_length=200)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------------- Projectos


class MilestoneIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    done: bool = False

    _s = field_validator("title", mode="before")(_strip)


class MilestoneOut(ORM):
    id: str
    title: str
    due_date: date | None
    done_at: datetime | None
    position: int


class ProjectLinkIn(BaseModel):
    kind: LinkKind = "link"
    title: str = Field(default="", max_length=200)
    # Endereço http(s); para o tipo «pasta», o caminho de uma pasta local (ex.: ~/Documents/Projectos/q360).
    url: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _url(self) -> ProjectLinkIn:
        from pathlib import Path

        if self.kind == "folder":
            p = Path(self.url).expanduser()
            if not p.is_absolute():
                raise ValueError("Indique o caminho completo da pasta (ex.: ~/Documents/Projectos/q360).")
            if not p.is_dir():
                raise ValueError("A pasta não existe.")
            self.url = str(p)
        else:
            self.url = str(AnyHttpUrl(self.url))
        return self


class ProjectLinkOut(ORM):
    id: str
    kind: str
    title: str
    url: str


class ProjectBase(BaseModel):
    name: str = Name
    description: str = Field(default="", max_length=20000)
    category: str = Field(default="", max_length=80)
    status: ProjectStatus = "planned"
    priority: Priority = "medium"
    start_date: date | None = None
    due_date: date | None = None
    objectives: str = Field(default="", max_length=20000)
    expected_results: str = Field(default="", max_length=20000)
    blocked_reason: str = Field(default="", max_length=5000)

    _s = field_validator("name", "category", mode="before")(_strip)

    @model_validator(mode="after")
    def _dates(self) -> ProjectBase:
        if self.start_date and self.due_date and self.due_date < self.start_date:
            raise ValueError("A data de fim não pode ser anterior à data de início.")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    category: str | None = Field(default=None, max_length=80)
    status: ProjectStatus | None = None
    priority: Priority | None = None
    start_date: date | None = None
    due_date: date | None = None
    objectives: str | None = Field(default=None, max_length=20000)
    expected_results: str | None = Field(default=None, max_length=20000)
    blocked_reason: str | None = Field(default=None, max_length=5000)

    _s = field_validator("name", "category", mode="before")(_strip)


class ProjectProgress(BaseModel):
    """Progresso = tarefas de topo concluídas / tarefas de topo não arquivadas.

    ``percent`` é ``None`` quando o projecto não tem tarefas (sem critério mensurável).
    """

    tasks_total: int
    tasks_done: int
    milestones_total: int
    milestones_done: int
    percent: int | None
    overdue_tasks: int


class ProjectOut(ORM):
    id: str
    name: str
    description: str
    category: str
    status: str
    priority: str
    start_date: date | None
    due_date: date | None
    objectives: str
    expected_results: str
    blocked_reason: str
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    progress: ProjectProgress | None = None
    last_activity_at: datetime | None = None
    stale: bool = False


class ProjectDetail(ProjectOut):
    milestones: list[MilestoneOut]
    links: list[ProjectLinkOut]


# --------------------------------------------------------------------------- Tarefas


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    project_id: str | None = None
    parent_id: str | None = None
    status: TaskStatus = "todo"
    priority: Priority = "medium"
    due_at: datetime | None = None
    estimate_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    completion_criteria: str = Field(default="", max_length=5000)
    blocked_reason: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=20000)
    goal_id: str | None = None
    version_id: str | None = None

    _s = field_validator("title", mode="before")(_strip)

    @field_validator("due_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("A data/hora deve incluir fuso horário (ISO 8601).")
        return v


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20000)
    project_id: str | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    estimate_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    completion_criteria: str | None = Field(default=None, max_length=5000)
    blocked_reason: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=20000)
    position: int | None = None
    goal_id: str | None = None
    version_id: str | None = None

    _s = field_validator("title", mode="before")(_strip)

    @field_validator("due_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("A data/hora deve incluir fuso horário (ISO 8601).")
        return v


class TaskOut(ORM):
    id: str
    title: str
    description: str
    project_id: str | None
    parent_id: str | None
    status: str
    priority: str
    due_at: datetime | None
    estimate_minutes: int | None
    completion_criteria: str
    blocked_reason: str
    notes: str
    position: int
    completed_at: datetime | None
    archived_at: datetime | None
    postponed_count: int
    created_at: datetime
    updated_at: datetime
    overdue: bool = False
    subtasks_total: int = 0
    subtasks_done: int = 0
    project_name: str | None = None
    number: int | None = None
    started_at: datetime | None = None
    blocked_seconds: int = 0
    goal_id: str | None = None
    version_id: str | None = None
    depends_on: list[str] = []
    blocked_by_open: int = 0


class TaskDetail(TaskOut):
    subtasks: list[TaskOut] = []


class DependencyIn(BaseModel):
    depends_on_id: str


class FocusStart(BaseModel):
    task_id: str | None = None
    project_id: str | None = None
    note: str = Field(default="", max_length=2000)


class FocusLog(BaseModel):
    """Registo manual de uma sessão de foco já concluída."""

    task_id: str | None = None
    project_id: str | None = None
    started_at: datetime
    minutes: int = Field(ge=1, le=60 * 12)
    note: str = Field(default="", max_length=2000)


class FocusOut(ORM):
    id: str
    task_id: str | None
    project_id: str | None
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int
    note: str


# --------------------------------------------------------------------------- Checklists


class ChecklistItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    section: str = Field(default="", max_length=120)
    done: bool = False

    _s = field_validator("text", "section", mode="before")(_strip)


class ChecklistItemUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    section: str | None = Field(default=None, max_length=120)
    done: bool | None = None
    position: int | None = None


class ChecklistItemOut(ORM):
    id: str
    section: str
    text: str
    done: bool
    position: int


class ChecklistCreate(BaseModel):
    title: str = Name
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="", max_length=80)
    is_template: bool = False
    project_id: str | None = None
    task_id: str | None = None
    items: list[ChecklistItemIn] = Field(default_factory=list, max_length=500)

    _s = field_validator("title", mode="before")(_strip)


class ChecklistUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, max_length=80)
    project_id: str | None = None
    task_id: str | None = None


class ChecklistOut(ORM):
    id: str
    title: str
    description: str
    category: str
    is_template: bool
    builtin_key: str | None
    project_id: str | None
    task_id: str | None
    source_template_id: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ChecklistItemOut]
    percent: int = 0


class InstantiateTemplate(BaseModel):
    project_id: str | None = None
    task_id: str | None = None
    title: str | None = Field(default=None, max_length=200)


class ProjectFromTemplate(BaseModel):
    template_id: str
    name: str = Name
    description: str = Field(default="", max_length=20000)
    category: str = Field(default="", max_length=80)
    priority: Priority = "medium"
    create_tasks: bool = True


# --------------------------------------------------------------------------- Notas


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=500_000)
    kind: NoteKind = "note"
    in_knowledge_base: bool = False
    project_id: str | None = None
    task_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    source_url: str = Field(default="", max_length=2000)
    pinned: bool = False

    _s = field_validator("title", mode="before")(_strip)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        clean = []
        for t in v:
            t = t.strip().lower()
            if t and len(t) <= 40 and t not in clean:
                clean.append(t)
        return clean


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, max_length=500_000)
    kind: NoteKind | None = None
    in_knowledge_base: bool | None = None
    project_id: str | None = None
    task_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=30)
    source_url: str | None = Field(default=None, max_length=2000)
    pinned: bool | None = None
    # Revisão que o cliente conhece; se divergir, a gravação é recusada (409).
    base_revision: int | None = None


class NoteOut(ORM):
    id: str
    title: str
    content: str
    kind: str
    in_knowledge_base: bool
    project_id: str | None
    task_id: str | None
    tags: list[str]
    source_url: str
    pinned: bool
    archived_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class NoteSummary(ORM):
    id: str
    title: str
    kind: str
    in_knowledge_base: bool
    project_id: str | None
    task_id: str | None
    tags: list[str]
    pinned: bool
    archived_at: datetime | None
    revision: int
    updated_at: datetime
    excerpt: str = ""


class NoteRevisionOut(ORM):
    id: str
    revision: int
    title: str
    content: str
    created_at: datetime


class RelationIn(BaseModel):
    source_type: EntityType
    source_id: str
    target_type: EntityType
    target_id: str
    label: str = Field(default="relacionado", min_length=1, max_length=60)


class RelationOut(ORM):
    id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    label: str
    created_at: datetime


class GraphNode(BaseModel):
    id: str
    type: str
    entity_id: str
    label: str
    kind: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    implicit: bool = False


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# --------------------------------------------------------------------------- Agenda


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    kind: Literal["event", "work_block"] = "event"
    start_at: datetime
    end_at: datetime
    all_day: bool = False
    location: str = Field(default="", max_length=300)
    project_id: str | None = None
    task_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> EventBase:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("As datas devem incluir fuso horário (ISO 8601).")
        if self.end_at <= self.start_at:
            raise ValueError("O fim tem de ser posterior ao início.")
        return self


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    kind: Literal["event", "work_block"] | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = Field(default=None, max_length=300)
    project_id: str | None = None
    task_id: str | None = None


class EventOut(ORM):
    id: str
    title: str
    description: str
    kind: str
    start_at: datetime
    end_at: datetime
    all_day: bool
    location: str
    project_id: str | None
    task_id: str | None
    created_at: datetime
    updated_at: datetime


class ReviewGoal(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    done: bool = False


class ReviewUpdate(BaseModel):
    goals: list[ReviewGoal] | None = Field(default=None, max_length=30)
    wins: str | None = Field(default=None, max_length=10000)
    blockers: str | None = Field(default=None, max_length=10000)
    reflection: str | None = Field(default=None, max_length=10000)
    next_plan: str | None = Field(default=None, max_length=10000)
    closed: bool | None = None


class ReviewOut(ORM):
    id: str
    kind: str
    period_start: date
    goals: list[ReviewGoal]
    wins: str
    blockers: str
    reflection: str
    next_plan: str
    closed_at: datetime | None
    updated_at: datetime


class ReviewContext(BaseModel):
    """Dados reais do período, calculados para apoiar a revisão."""

    review: ReviewOut
    completed: list[TaskOut]
    postponed: list[TaskOut]
    overdue: list[TaskOut]
    due_next: list[TaskOut]
    focus_minutes: int
    events: list[EventOut]


# --------------------------------------------------------------------------- Actividade e notificações


class ActivityOut(ORM):
    id: str
    entity_type: str
    entity_id: str
    action: str
    summary: str
    created_at: datetime


class NotificationOut(ORM):
    id: str
    category: str
    level: str
    title: str
    body: str
    link: str
    created_at: datetime
    read_at: datetime | None
    native_sent: bool


class SearchHit(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    snippet: str
    route: str


class SearchResult(BaseModel):
    engine: str
    query: str
    hits: list[SearchHit]


class SettingsPatch(BaseModel):
    values: dict[str, Any]


class ConfirmBody(BaseModel):
    confirm: bool = False


class GoalIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    project_id: str | None = None
    target_date: date | None = None
    status: Literal["active", "achieved", "dropped"] = "active"


class VersionIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=5000)
    target_date: date | None = None
    status: Literal["planned", "in_progress", "released"] = "planned"
    git_tag: str = Field(default="", max_length=100)
