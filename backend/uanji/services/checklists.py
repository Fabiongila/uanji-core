"""Checklists, modelos reutilizáveis e criação de projectos a partir de modelos."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import schemas
from ..errors import ConfirmationRequired, ValidationFailed
from ..models import Checklist, ChecklistItem, Project, Task
from . import projects as project_service
from . import tasks as task_service
from .common import get_or_404, index_entity, log_activity, unindex_entity

BUILTIN_TEMPLATES: list[dict[str, object]] = [
    {
        "key": "software-project",
        "title": "Novo projecto de software",
        "category": "Software",
        "description": "Arranque de um projecto de software com fundações sólidas.",
        "sections": {
            "Definição": [
                "Descrever o problema e o utilizador-alvo",
                "Definir objectivos e critérios de sucesso",
                "Delimitar o âmbito da primeira versão",
            ],
            "Fundações": [
                "Criar repositório Git e README",
                "Escolher stack e registar a decisão de arquitectura",
                "Configurar lint, formatação e verificação de tipos",
                "Configurar testes automatizados",
                "Configurar variáveis de ambiente (.env.example)",
            ],
            "Entrega": [
                "Definir pipeline de CI",
                "Documentar execução local",
                "Planear a primeira release",
            ],
        },
    },
    {
        "key": "api-development",
        "title": "Desenvolvimento de uma API",
        "category": "Software",
        "description": "Desenho, implementação e documentação de uma API.",
        "sections": {
            "Desenho": [
                "Identificar recursos e operações",
                "Definir contratos (OpenAPI) e códigos de erro",
                "Definir autenticação e autorização",
                "Definir paginação, filtros e versionamento",
            ],
            "Implementação": [
                "Validar todas as entradas",
                "Implementar tratamento centralizado de erros",
                "Implementar migrações da base de dados",
                "Adicionar logs estruturados sem dados sensíveis",
            ],
            "Qualidade": [
                "Testes de unidade e de API",
                "Testes de permissões",
                "Limites de taxa e timeouts",
                "Documentação publicada",
            ],
        },
    },
    {
        "key": "code-review",
        "title": "Revisão de código",
        "category": "Software",
        "description": "Pontos a verificar antes de aprovar alterações.",
        "sections": {
            "Correcção": [
                "A alteração resolve o problema descrito",
                "Casos-limite e erros tratados",
                "Sem regressões nos testes existentes",
            ],
            "Qualidade": [
                "Nomes claros e código legível",
                "Sem duplicação desnecessária",
                "Testes adequados à alteração",
            ],
            "Segurança": [
                "Entradas validadas",
                "Sem segredos no código ou logs",
                "Dependências novas justificadas",
            ],
        },
    },
    {
        "key": "app-release",
        "title": "Publicação de uma aplicação",
        "category": "Software",
        "description": "Preparação e verificação de uma release.",
        "sections": {
            "Preparação": [
                "Actualizar número de versão e changelog",
                "Executar todos os testes",
                "Rever dependências e vulnerabilidades",
            ],
            "Publicação": [
                "Gerar build de produção",
                "Validar instalação num ambiente limpo",
                "Criar tag e notas de release",
            ],
            "Pós-publicação": [
                "Monitorizar erros e feedback",
                "Confirmar backups e plano de rollback",
            ],
        },
    },
    {
        "key": "data-analysis",
        "title": "Preparação de um projecto de análise de dados",
        "category": "Dados",
        "description": "Estruturar uma análise de dados reprodutível.",
        "sections": {
            "Pergunta": [
                "Formular a pergunta de negócio",
                "Definir métricas e hipóteses",
            ],
            "Ambiente": [
                "Criar ambiente virtual e fixar dependências",
                "Organizar estrutura data/raw, data/processed, notebooks",
            ],
            "Análise": [
                "Análise exploratória documentada",
                "Limpeza e transformação reprodutíveis",
                "Validar resultados com amostras",
                "Comunicar conclusões e limitações",
            ],
        },
    },
    {
        "key": "dataset-validation",
        "title": "Recolha e validação de datasets",
        "category": "Dados",
        "description": "Garantir a qualidade e a legalidade de um dataset.",
        "sections": {
            "Recolha": [
                "Confirmar origem e licença dos dados",
                "Registar data e método de recolha",
                "Verificar dados pessoais e consentimento",
            ],
            "Validação": [
                "Verificar valores em falta e duplicados",
                "Verificar distribuição das classes",
                "Verificar qualidade das anotações (visão computacional)",
                "Separar treino, validação e teste sem fugas de dados",
            ],
            "Documentação": [
                "Escrever ficha do dataset (datasheet)",
                "Versionar o dataset",
            ],
        },
    },
    {
        "key": "weekly-review",
        "title": "Revisão semanal",
        "category": "Planeamento",
        "description": "Rotina semanal de revisão e planeamento.",
        "sections": {
            "Rever": [
                "Rever tarefas concluídas da semana",
                "Rever tarefas atrasadas e adiadas",
                "Rever projectos bloqueados ou sem actividade",
                "Esvaziar notas soltas e ideias",
            ],
            "Planear": [
                "Definir 3 resultados para a próxima semana",
                "Reservar blocos de foco na agenda",
                "Confirmar prazos da próxima semana",
            ],
        },
    },
]


def seed_builtin_templates(db: Session) -> int:
    """Cria os modelos de origem que ainda não existem. Não sobrescreve edições do utilizador."""
    existing = set(db.scalars(select(Checklist.builtin_key).where(Checklist.builtin_key.is_not(None))))
    created = 0
    for tpl in BUILTIN_TEMPLATES:
        key = str(tpl["key"])
        if key in existing:
            continue
        c = Checklist(
            title=str(tpl["title"]),
            description=str(tpl["description"]),
            category=str(tpl["category"]),
            is_template=True,
            builtin_key=key,
        )
        pos = 0
        sections = tpl["sections"]
        assert isinstance(sections, dict)
        for section, items in sections.items():
            for text in items:
                c.items.append(ChecklistItem(section=section, text=text, position=pos))
                pos += 1
        db.add(c)
        db.flush()
        _index(db, c)
        created += 1
    return created


def _index(db: Session, c: Checklist) -> None:
    index_entity(db, "checklist", c.id, c.title, c.description + "\n" + "\n".join(i.text for i in c.items))


def to_out(c: Checklist) -> schemas.ChecklistOut:
    out = schemas.ChecklistOut.model_validate(c)
    total = len(c.items)
    out.percent = round(sum(1 for i in c.items if i.done) * 100 / total) if total else 0
    return out


def _load(db: Session, checklist_id: str) -> Checklist:
    c = db.scalars(select(Checklist).where(Checklist.id == checklist_id).options(selectinload(Checklist.items))).first()
    if c is None:
        return get_or_404(db, Checklist, checklist_id)
    return c


def list_checklists(
    db: Session, is_template: bool | None = None, project_id: str | None = None, task_id: str | None = None
) -> list[schemas.ChecklistOut]:
    stmt = select(Checklist).options(selectinload(Checklist.items))
    if is_template is not None:
        stmt = stmt.where(Checklist.is_template == is_template)
    if project_id:
        stmt = stmt.where(Checklist.project_id == project_id)
    if task_id:
        stmt = stmt.where(Checklist.task_id == task_id)
    return [to_out(c) for c in db.scalars(stmt.order_by(Checklist.is_template.desc(), Checklist.title))]


def get_checklist(db: Session, checklist_id: str) -> schemas.ChecklistOut:
    return to_out(_load(db, checklist_id))


def _check_links(db: Session, project_id: str | None, task_id: str | None) -> None:
    if project_id:
        get_or_404(db, Project, project_id)
    if task_id:
        get_or_404(db, Task, task_id)


def create_checklist(db: Session, data: schemas.ChecklistCreate) -> Checklist:
    _check_links(db, data.project_id, data.task_id)
    if data.is_template and (data.project_id or data.task_id):
        raise ValidationFailed("Um modelo não pode estar associado a um projecto ou tarefa.")
    c = Checklist(**data.model_dump(exclude={"items"}))
    for pos, item in enumerate(data.items):
        c.items.append(ChecklistItem(position=pos, **item.model_dump()))
    db.add(c)
    db.flush()
    _index(db, c)
    log_activity(db, "checklist", c.id, "created", f"{'Modelo' if c.is_template else 'Checklist'} criado: {c.title}")
    return c


def update_checklist(db: Session, checklist_id: str, data: schemas.ChecklistUpdate) -> Checklist:
    c = _load(db, checklist_id)
    changes = data.model_dump(exclude_unset=True)
    _check_links(db, changes.get("project_id"), changes.get("task_id"))
    for k, v in changes.items():
        setattr(c, k, v)
    db.flush()
    _index(db, c)
    return c


def delete_checklist(db: Session, checklist_id: str, confirm: bool) -> None:
    c = _load(db, checklist_id)
    if not confirm:
        raise ConfirmationRequired("Eliminar a checklist é irreversível. Confirme a operação.")
    unindex_entity(db, "checklist", c.id)
    log_activity(db, "checklist", c.id, "deleted", f"Checklist eliminada: {c.title}")
    db.delete(c)


def add_item(db: Session, checklist_id: str, data: schemas.ChecklistItemIn) -> ChecklistItem:
    c = _load(db, checklist_id)
    pos = (db.scalar(select(func.max(ChecklistItem.position)).where(ChecklistItem.checklist_id == c.id)) or 0) + 1
    item = ChecklistItem(checklist_id=c.id, position=pos, **data.model_dump())
    db.add(item)
    db.flush()
    db.refresh(c)
    _index(db, c)
    return item


def update_item(db: Session, item_id: str, data: schemas.ChecklistItemUpdate) -> ChecklistItem:
    item = get_or_404(db, ChecklistItem, item_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.flush()
    return item


def delete_item(db: Session, item_id: str) -> None:
    db.delete(get_or_404(db, ChecklistItem, item_id))


def duplicate(
    db: Session,
    checklist_id: str,
    *,
    as_template: bool,
    project_id: str | None = None,
    task_id: str | None = None,
    title: str | None = None,
) -> Checklist:
    src = _load(db, checklist_id)
    _check_links(db, project_id, task_id)
    c = Checklist(
        title=title or (src.title if src.is_template and not as_template else f"{src.title} (cópia)"),
        description=src.description,
        category=src.category,
        is_template=as_template,
        project_id=None if as_template else project_id,
        task_id=None if as_template else task_id,
        source_template_id=src.id if src.is_template else src.source_template_id,
    )
    for item in src.items:
        c.items.append(
            ChecklistItem(
                section=item.section,
                text=item.text,
                position=item.position,
                done=False if src.is_template or as_template else item.done,
            )
        )
    db.add(c)
    db.flush()
    _index(db, c)
    log_activity(db, "checklist", c.id, "created", f"Checklist criada a partir de «{src.title}»")
    return c


def project_from_template(db: Session, data: schemas.ProjectFromTemplate) -> Project:
    """Cria (numa única transacção) projecto + checklist + tarefas a partir de um modelo."""
    tpl = _load(db, data.template_id)
    if not tpl.is_template:
        raise ValidationFailed("A checklist indicada não é um modelo.")
    project = project_service.create_project(
        db,
        schemas.ProjectCreate(
            name=data.name,
            description=data.description or tpl.description,
            category=data.category or tpl.category,
            priority=data.priority,
            status="planned",
        ),
    )
    duplicate(db, tpl.id, as_template=False, project_id=project.id, title=tpl.title)
    if data.create_tasks:
        for item in tpl.items:
            task_service.create_task(
                db,
                schemas.TaskCreate(
                    title=item.text,
                    project_id=project.id,
                    description=f"Secção: {item.section}" if item.section else "",
                ),
            )
    log_activity(db, "project", project.id, "from_template", f"Projecto criado a partir do modelo «{tpl.title}»")
    return project
