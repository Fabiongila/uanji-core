"""Motor de automações: validação, versionamento, execução e agendamento.

Definição de uma automação (versão)::

    {
      "trigger":    {"type": "manual" | "schedule" | "task_completed" | "deadline_approaching",
                     "config": {...}},
      "conditions": [{"field": "trigger.project_id", "op": "eq", "value": "..."}],
      "steps":      [{"id": "s1", "action": "create_task", "params": {...}}],
      "ui":         {...}   # posições do construtor visual (opaco para o motor)
    }

Execução:
- Sequencial, pela ordem de ``steps``; cada etapa é confirmada (commit) separadamente.
- Uma falha interrompe a execução; as etapas anteriores **não** são revertidas.
- Falhas recuperáveis (ex.: base de dados ocupada) são repetidas até ``MAX_RETRIES``.
- ``idempotency_key`` único evita execuções duplicadas do mesmo evento de origem.
- O cancelamento é verificado entre etapas.
- Parâmetros aceitam ``{{caminho.no.contexto}}`` (substituição de texto, nunca avaliação).
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .. import runtime
from ..errors import AppError, ConfirmationRequired, Conflict, ValidationFailed
from ..models import Automation, AutomationRun, AutomationRunStep, AutomationVersion, Task, utcnow
from ..services import notifications as notification_service
from ..services.common import get_or_404, index_entity, local_tz, log_activity, unindex_entity
from .actions import ACTIONS, RecoverableError

log = logging.getLogger(__name__)

MAX_STEPS = 25
MAX_RETRIES = 2
RUN_TIMEOUT_SECONDS = 30
MAX_DEPTH = 3  # automações encadeadas (ex.: concluir tarefa → outra automação)
MIN_INTERVAL_MINUTES = 15

TriggerType = Literal["manual", "schedule", "task_completed", "deadline_approaching", "webhook", "github", "app_opened"]


# --------------------------------------------------------------------------- Definição


class ScheduleConfig(BaseModel):
    mode: Literal["interval", "daily", "once"]
    minutes: int | None = Field(default=None, ge=MIN_INTERVAL_MINUTES, le=60 * 24 * 7)
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    at: datetime | None = None

    @model_validator(mode="after")
    def _check(self) -> ScheduleConfig:
        if self.mode == "interval" and self.minutes is None:
            raise ValueError(f"Indique o intervalo em minutos (mínimo {MIN_INTERVAL_MINUTES}).")
        if self.mode == "daily" and not self.time:
            raise ValueError("Indique a hora (HH:MM).")
        if self.mode == "once" and (self.at is None or self.at.tzinfo is None):
            raise ValueError("Indique a data/hora com fuso horário.")
        if any(d < 0 or d > 6 for d in self.weekdays) or not self.weekdays:
            raise ValueError("Dias da semana inválidos (0 = segunda ... 6 = domingo).")
        return self


class TaskCompletedConfig(BaseModel):
    project_id: str | None = None


class DeadlineConfig(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)
    project_id: str | None = None


class GitHubTriggerConfig(BaseModel):
    repo_url: str = Field(pattern=r"^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?$")
    event: Literal["push", "pr_opened", "pr_merged", "issue_opened", "release"] = "push"
    branch: str = Field(default="", max_length=200)


class AppOpenedConfig(BaseModel):
    app: str = Field(min_length=1, max_length=120)


class Trigger(BaseModel):
    type: TriggerType = "manual"
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _config(self) -> Trigger:
        models: dict[str, type[BaseModel]] = {
            "schedule": ScheduleConfig,
            "task_completed": TaskCompletedConfig,
            "deadline_approaching": DeadlineConfig,
            "github": GitHubTriggerConfig,
            "app_opened": AppOpenedConfig,
        }
        model = models.get(self.type)
        if model is not None:
            self.config = model.model_validate(self.config).model_dump(mode="json")
        else:
            self.config = {}
        return self


class Condition(BaseModel):
    field: str = Field(pattern=r"^[a-zA-Z_][\w.]{0,80}$")
    op: Literal["eq", "neq", "contains", "exists", "not_exists"]
    value: Any = None


class Step(BaseModel):
    id: str = Field(pattern=r"^[\w-]{1,60}$")
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    # Nó «Condição» antes desta etapa: se falhar, a etapa é ignorada («skip») ou o fluxo pára («stop»).
    conditions: list[Condition] = Field(default_factory=list, max_length=10)
    on_false: Literal["skip", "stop"] = "skip"

    @field_validator("action")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ACTIONS:
            raise ValueError(f"Acção desconhecida: {v}")
        return v


class Definition(BaseModel):
    trigger: Trigger = Field(default_factory=Trigger)
    conditions: list[Condition] = Field(default_factory=list, max_length=10)
    steps: list[Step] = Field(min_length=1, max_length=MAX_STEPS)
    ui: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique(self) -> Definition:
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores de etapas repetidos.")
        return self


_TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)\s*\}\}")


def _lookup(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render(value: Any, ctx: dict[str, Any]) -> Any:
    """Substitui ``{{a.b}}`` por valores do contexto. Apenas texto; sem expressões."""
    if isinstance(value, str):
        whole = _TEMPLATE.fullmatch(value.strip())
        if whole:
            found = _lookup(ctx, whole.group(1))
            return found if found is not None else ""
        return _TEMPLATE.sub(lambda m: str(_lookup(ctx, m.group(1)) or ""), value)
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    return value


def validate_definition(raw: dict[str, Any]) -> tuple[Definition | None, list[dict[str, str]]]:
    """Valida estrutura e parâmetros de cada etapa. Devolve (definição, erros)."""
    try:
        d = Definition.model_validate(raw)
    except ValidationError as e:
        return None, [{"path": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in e.errors()]
    errors: list[dict[str, str]] = []
    for i, s in enumerate(d.steps):
        spec = ACTIONS[s.action]
        # Parâmetros com modelos {{...}} só podem ser verificados na execução; validamos os restantes
        # substituindo-os por um valor de exemplo.
        probe = _probe(s.params)
        try:
            spec.params.model_validate(probe)
        except ValidationError as e:
            for err in e.errors():
                errors.append(
                    {
                        "path": f"steps.{i}.params.{'.'.join(str(p) for p in err['loc'])}",
                        "message": err["msg"],
                        "step": s.id,
                    }
                )
    return (d if not errors else None), errors


def _probe(value: Any) -> Any:
    """Substitui modelos por um valor de exemplo para validar o resto dos parâmetros."""
    if isinstance(value, str) and _TEMPLATE.search(value):
        return "exemplo"
    if isinstance(value, dict):
        return {k: _probe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_probe(v) for v in value]
    return value


def _check_conditions(conds: list[Condition], ctx: dict[str, Any]) -> tuple[bool, str]:
    for c in conds:
        v = _lookup(ctx, c.field)
        if c.op == "eq":
            ok = v == c.value
        elif c.op == "neq":
            ok = v != c.value
        elif c.op == "contains":
            ok = c.value is not None and str(c.value).lower() in str(v or "").lower()
        elif c.op == "exists":
            ok = v not in (None, "")
        else:
            ok = v in (None, "")
        if not ok:
            return False, f"Condição não satisfeita: {c.field} {c.op} {c.value!r}"
    return True, ""


# --------------------------------------------------------------------------- CRUD e versões


def current_definition(db: Session, a: Automation) -> dict[str, Any]:
    v = db.scalars(
        select(AutomationVersion).where(
            AutomationVersion.automation_id == a.id, AutomationVersion.version == a.current_version
        )
    ).first()
    return v.definition if v else {}


def compute_next_run(db: Session, trigger: dict[str, Any], after: datetime | None = None) -> datetime | None:
    if trigger.get("type") != "schedule":
        return None
    cfg = ScheduleConfig.model_validate(trigger.get("config", {}))
    now = after or utcnow()
    if cfg.mode == "interval":
        assert cfg.minutes is not None
        return now + timedelta(minutes=cfg.minutes)
    if cfg.mode == "once":
        assert cfg.at is not None
        return cfg.at if cfg.at > now else None
    tz: ZoneInfo = local_tz(db)
    assert cfg.time is not None
    hh, mm = (int(x) for x in cfg.time.split(":"))
    local_now = now.astimezone(tz)
    for add in range(0, 8):
        day = (local_now + timedelta(days=add)).date()
        cand = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
        if cand > local_now and day.weekday() in cfg.weekdays:
            return cand
    return None


def _index(db: Session, a: Automation) -> None:
    index_entity(db, "automation", a.id, a.name, a.description)


def create_automation(
    db: Session, name: str, description: str, definition: dict[str, Any], enabled: bool = False
) -> Automation:
    d, errors = validate_definition(definition)
    if d is None:
        raise ValidationFailed("A automação tem erros de validação.", {"errors": errors})
    a = Automation(name=name, description=description, enabled=enabled, current_version=1, trigger_type=d.trigger.type)
    db.add(a)
    db.flush()
    db.add(AutomationVersion(automation_id=a.id, version=1, definition=d.model_dump(mode="json")))
    a.next_run_at = compute_next_run(db, d.trigger.model_dump()) if enabled else None
    _index(db, a)
    log_activity(db, "automation", a.id, "created", f"Automação criada: {name}")
    return a


def update_automation(
    db: Session,
    automation_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    definition: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> Automation:
    a = get_or_404(db, Automation, automation_id)
    if name is not None:
        a.name = name
    if description is not None:
        a.description = description
    if definition is not None:
        d, errors = validate_definition(definition)
        if d is None:
            raise ValidationFailed("A automação tem erros de validação.", {"errors": errors})
        new_def = d.model_dump(mode="json")
        if new_def != current_definition(db, a):
            a.current_version += 1
            db.add(AutomationVersion(automation_id=a.id, version=a.current_version, definition=new_def))
            a.trigger_type = d.trigger.type
            log_activity(db, "automation", a.id, "versioned", f"Automação «{a.name}» → versão {a.current_version}")
    if enabled is not None and enabled != a.enabled:
        a.enabled = enabled
        log_activity(
            db,
            "automation",
            a.id,
            "enabled" if enabled else "disabled",
            f"Automação {'activada' if enabled else 'desactivada'}: {a.name}",
        )
    db.flush()
    trig = current_definition(db, a).get("trigger", {})
    a.next_run_at = compute_next_run(db, trig) if a.enabled else None
    _index(db, a)
    return a


def delete_automation(db: Session, automation_id: str, confirm: bool) -> None:
    a = get_or_404(db, Automation, automation_id)
    if not confirm:
        raise ConfirmationRequired("Eliminar a automação remove também o histórico de execuções.")
    unindex_entity(db, "automation", a.id)
    log_activity(db, "automation", a.id, "deleted", f"Automação eliminada: {a.name}")
    db.delete(a)


def rollback_version(db: Session, automation_id: str, version: int) -> Automation:
    a = get_or_404(db, Automation, automation_id)
    v = db.scalars(
        select(AutomationVersion).where(AutomationVersion.automation_id == a.id, AutomationVersion.version == version)
    ).first()
    if v is None:
        raise ValidationFailed("Versão inexistente.")
    return update_automation(db, automation_id, definition=v.definition)


# --------------------------------------------------------------------------- Execução


def _is_recoverable(exc: Exception) -> bool:
    if isinstance(exc, RecoverableError):
        return True
    if isinstance(exc, OperationalError | sqlite3.OperationalError):
        return "locked" in str(exc).lower() or "busy" in str(exc).lower()
    return False


def execute(
    automation_id: str,
    trigger: str,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    depth: int = 0,
) -> str | None:
    """Executa uma automação. Devolve o id da execução, ou ``None`` se for duplicada.

    Abre as suas próprias sessões: cada etapa é confirmada separadamente para que o
    histórico reflicta exactamente o que foi aplicado.
    """
    database = runtime.get_database()
    payload = payload or {}
    if depth >= MAX_DEPTH:
        log.warning("Encadeamento de automações excedeu o limite (%s)", MAX_DEPTH)
        return None

    with database.session() as db:
        a = get_or_404(db, Automation, automation_id)
        raw_def = current_definition(db, a)
        definition = Definition.model_validate(raw_def)
        running = db.scalar(
            select(AutomationRun.id).where(
                AutomationRun.automation_id == a.id,
                AutomationRun.status == "running",
                AutomationRun.started_at > utcnow() - timedelta(seconds=RUN_TIMEOUT_SECONDS * 2),
            )
        )
        if running and trigger == "manual":
            raise Conflict("Esta automação já está em execução.")
        run = AutomationRun(
            automation_id=a.id,
            version=a.current_version,
            trigger=trigger,
            idempotency_key=idempotency_key,
            status="running",
            context={"trigger": payload},
        )
        try:
            with db.begin_nested():
                db.add(run)
        except IntegrityError:
            return None
        a.last_run_at = run.started_at
        run_id = run.id
        ctx: dict[str, Any] = {
            "automation": {"id": a.id, "name": a.name, "version": a.current_version},
            "trigger": payload,
            "now": {"iso": utcnow().isoformat(), "date": utcnow().astimezone(local_tz(db)).date().isoformat()},
            "steps": {},
        }

    ok, reason = _check_conditions(definition.conditions, ctx)
    started = time.monotonic()
    final_status, final_error = "success", ""
    if not ok:
        final_status = "cancelled"
        final_error = reason
    else:
        for index, step in enumerate(definition.steps):
            with database.session() as db:
                r = db.get(AutomationRun, run_id)
                assert r is not None
                if r.cancel_requested:
                    final_status, final_error = "cancelled", "Cancelada pelo utilizador."
                    break
            if time.monotonic() - started > RUN_TIMEOUT_SECONDS:
                final_status, final_error = "failed", f"Tempo limite de {RUN_TIMEOUT_SECONDS}s excedido."
                break
            gate_ok, gate_reason = _check_conditions(step.conditions, ctx)
            if not gate_ok:
                with database.session() as db:
                    db.add(
                        AutomationRunStep(
                            run_id=run_id,
                            index=index,
                            node_id=step.id,
                            action=step.action,
                            status="skipped",
                            attempts=0,
                            input={},
                            output={},
                            error=gate_reason,
                            finished_at=utcnow(),
                        )
                    )
                if step.on_false == "stop":
                    final_status = "cancelled"
                    final_error = f"Fluxo terminado na condição antes de «{step.id}»: {gate_reason}"
                    break
                continue
            status, error, output, attempts, params = _run_step(database, step, ctx, run_id, depth)
            with database.session() as db:
                db.add(
                    AutomationRunStep(
                        run_id=run_id,
                        index=index,
                        node_id=step.id,
                        action=step.action,
                        status=status,
                        attempts=attempts,
                        input=_jsonable(params),
                        output=_jsonable(output),
                        error=error,
                        finished_at=utcnow(),
                    )
                )
            if status != "success":
                final_status, final_error = "failed", f"Etapa «{step.id}» ({step.action}): {error}"
                break
            ctx["steps"][step.id] = output

    with database.session() as db:
        r = db.get(AutomationRun, run_id)
        auto = db.get(Automation, automation_id)
        assert r is not None and auto is not None
        r.status = final_status
        r.error = final_error
        r.finished_at = utcnow()
        r.duration_ms = int((time.monotonic() - started) * 1000)
        r.context = _jsonable({"trigger": payload, "steps": ctx["steps"]})
        log_activity(
            db,
            "automation",
            auto.id,
            f"run_{final_status}",
            f"Execução de «{auto.name}»: {final_status}" + (f" — {final_error[:200]}" if final_error else ""),
        )
        if final_status == "failed":
            notification_service.create(
                db,
                category="automation",
                level="error",
                title=f"Falha na automação «{auto.name}»",
                body=final_error[:500],
                link=f"/automations/{auto.id}",
                dedupe_key=f"run-failed:{run_id}",
            )
    return run_id


def _run_step(
    database: Any, step: Step, ctx: dict[str, Any], run_id: str, depth: int
) -> tuple[str, str, dict[str, Any], int, dict[str, Any]]:
    spec = ACTIONS[step.action]
    params = render(step.params, ctx)
    attempts = 0
    while True:
        attempts += 1
        try:
            parsed = spec.params.model_validate(params)
            with database.session() as db:
                db.info["automation_depth"] = depth + 1
                db.info["automation_run_id"] = run_id
                out = spec.run(db, parsed, ctx)
            return "success", "", out, attempts, params
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
            return "failed", f"Parâmetros inválidos — {msg}", {}, attempts, params
        except AppError as e:
            return "failed", e.message, {}, attempts, params
        except Exception as e:
            if _is_recoverable(e) and attempts <= MAX_RETRIES:
                time.sleep(0.3 * attempts)
                continue
            log.exception("Falha na etapa %s", step.id)
            return "failed", f"{type(e).__name__}: {e}"[:500], {}, attempts, params


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, str | int | float | bool) or v is None:
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def request_cancel(db: Session, run_id: str) -> AutomationRun:
    r = get_or_404(db, AutomationRun, run_id)
    if r.status not in ("pending", "running"):
        raise Conflict("A execução já terminou.")
    r.cancel_requested = True
    return r


# --------------------------------------------------------------------------- Gatilhos


def on_task_completed(_: str, payload: dict[str, Any]) -> None:
    depth = int(payload.get("_depth", 0))
    with runtime.get_database().session() as db:
        autos = db.scalars(
            select(Automation).where(Automation.enabled.is_(True), Automation.trigger_type == "task_completed")
        ).all()
        targets = []
        for a in autos:
            cfg = current_definition(db, a).get("trigger", {}).get("config", {})
            if cfg.get("project_id") and cfg["project_id"] != payload.get("project_id"):
                continue
            targets.append(a.id)
    # Normaliza a data para que a chave seja estável independentemente do formato textual.
    completed = datetime.fromisoformat(str(payload["completed_at"]).replace("Z", "+00:00")).astimezone(UTC)
    clean = {k: v for k, v in payload.items() if not k.startswith("_")}
    for aid in targets:
        execute(
            aid,
            "task_completed",
            clean,
            idempotency_key=f"{aid}:task:{payload['task_id']}:{completed.isoformat()}",
            depth=depth,
        )


# --------------------------------------------------------------------------- Gatilhos externos


def create_webhook_secret(db: Session, automation_id: str) -> str:
    """Gera (ou substitui) o segredo do webhook. Só o hash fica guardado; o segredo é mostrado uma vez."""
    import hashlib
    import secrets as _secrets

    a = get_or_404(db, Automation, automation_id)
    secret = _secrets.token_urlsafe(24)
    a.webhook_secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    log_activity(db, "automation", a.id, "webhook_secret", f"Novo segredo de webhook para «{a.name}»")
    return secret


def check_webhook(db: Session, automation_id: str, secret: str) -> Automation:
    import hashlib
    import hmac

    a = db.get(Automation, automation_id)
    if a is None or not a.webhook_secret_hash or not secret:
        raise ValidationFailed("Webhook desconhecido ou sem segredo.")
    if not hmac.compare_digest(a.webhook_secret_hash, hashlib.sha256(secret.encode()).hexdigest()):
        raise ValidationFailed("Segredo do webhook inválido.")
    if not a.enabled or a.trigger_type != "webhook":
        raise Conflict("A automação está desactivada ou não usa o gatilho webhook.")
    return a


def on_app_activated(app: str, now: datetime | None = None) -> list[str]:
    """Chamado pelo monitor de actividade quando uma aplicação passa para primeiro plano."""
    now = now or utcnow()
    targets = []
    with runtime.get_database().session() as db:
        for a in db.scalars(
            select(Automation).where(Automation.enabled.is_(True), Automation.trigger_type == "app_opened")
        ):
            want = str(current_definition(db, a).get("trigger", {}).get("config", {}).get("app", ""))
            if want and want.lower() in app.lower():
                targets.append(a.id)
    runs = []
    bucket = now.strftime("%Y%m%d%H") + str(now.minute // 30)  # no máximo uma vez a cada 30 min
    for aid in targets:
        rid = execute(aid, "app_opened", {"app": app, "at": now.isoformat()}, idempotency_key=f"{aid}:app:{bucket}")
        if rid:
            runs.append(rid)
    return runs


GITHUB_POLL_MINUTES = 5


def _github_events(db: Session, a: Automation, cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Novos eventos desde a última verificação. Na primeira verificação só regista a referência."""
    from ..integrations.github import GitHubAdapter, parse_repo

    owner, repo = parse_repo(cfg["repo_url"].rstrip("/"))
    gh = GitHubAdapter()
    state = dict(a.trigger_state or {})
    seen: list[str] = list(state.get("seen", []))
    event = cfg.get("event", "push")
    items: list[tuple[str, dict[str, Any]]] = []
    if event == "push":
        params: dict[str, Any] = {"per_page": 20}
        if cfg.get("branch"):
            params["sha"] = cfg["branch"]
        for c in gh.get_fresh(db, f"/repos/{owner}/{repo}/commits", params):
            items.append(
                (
                    c.get("sha", ""),
                    {
                        "event": "push",
                        "repo": f"{owner}/{repo}",
                        "sha": c.get("sha", "")[:7],
                        "message": (c.get("commit", {}).get("message") or "").split("\n")[0][:300],
                        "author": (c.get("commit", {}).get("author") or {}).get("name"),
                        "url": c.get("html_url"),
                        "branch": cfg.get("branch") or "",
                    },
                )
            )
    elif event in ("pr_opened", "pr_merged"):
        for p in gh.get_fresh(
            db, f"/repos/{owner}/{repo}/pulls", {"state": "all", "per_page": 20, "sort": "updated", "direction": "desc"}
        ):
            if event == "pr_merged" and not p.get("merged_at"):
                continue
            items.append(
                (
                    f"{event}:{p.get('number')}",
                    {
                        "event": event,
                        "repo": f"{owner}/{repo}",
                        "number": p.get("number"),
                        "title": p.get("title"),
                        "author": (p.get("user") or {}).get("login"),
                        "url": p.get("html_url"),
                        "branch": (p.get("head") or {}).get("ref"),
                    },
                )
            )
    elif event == "issue_opened":
        for i in gh.get_fresh(db, f"/repos/{owner}/{repo}/issues", {"state": "open", "per_page": 20}):
            if "pull_request" in i:
                continue
            items.append(
                (
                    f"issue:{i.get('number')}",
                    {
                        "event": event,
                        "repo": f"{owner}/{repo}",
                        "number": i.get("number"),
                        "title": i.get("title"),
                        "author": (i.get("user") or {}).get("login"),
                        "url": i.get("html_url"),
                    },
                )
            )
    elif event == "release":
        for r in gh.get_fresh(db, f"/repos/{owner}/{repo}/releases", {"per_page": 10}):
            items.append(
                (
                    f"release:{r.get('id')}",
                    {
                        "event": event,
                        "repo": f"{owner}/{repo}",
                        "tag": r.get("tag_name"),
                        "title": r.get("name"),
                        "url": r.get("html_url"),
                    },
                )
            )
    first = "seen" not in state
    new = [(k, payload) for k, payload in items if k and k not in seen]
    state["seen"] = ([k for k, _ in items] + seen)[:200]
    state["checked_at"] = utcnow().isoformat()
    a.trigger_state = state
    return [] if first else list(reversed(new))[:10]


def poll_github() -> list[str]:
    """Verifica eventos GitHub das automações com esse gatilho (no máximo de 5 em 5 minutos)."""
    due: list[tuple[str, str, dict[str, Any]]] = []
    now = utcnow()
    with runtime.get_database().session() as db:
        for a in db.scalars(
            select(Automation).where(Automation.enabled.is_(True), Automation.trigger_type == "github")
        ):
            checked = (a.trigger_state or {}).get("checked_at")
            if checked and now - datetime.fromisoformat(checked) < timedelta(minutes=GITHUB_POLL_MINUTES):
                continue
            cfg = current_definition(db, a).get("trigger", {}).get("config", {})
            try:
                for key, payload in _github_events(db, a, cfg):
                    due.append((a.id, key, payload))
            except AppError as e:
                a.trigger_state = {**(a.trigger_state or {}), "checked_at": now.isoformat(), "error": e.message}
                log.warning("Gatilho GitHub de %s: %s", a.name, e.message)
    runs = []
    for aid, key, payload in due:
        rid = execute(aid, "github", payload, idempotency_key=f"{aid}:gh:{key}")
        if rid:
            runs.append(rid)
    return runs


def scheduler_tick() -> list[str]:
    """Executa automações programadas e de prazo. Chamado periodicamente."""
    runs: list[str] = []
    now = utcnow()
    due: list[tuple[str, str, dict[str, Any], str]] = []
    with runtime.get_database().session() as db:
        for a in db.scalars(
            select(Automation).where(
                Automation.enabled.is_(True),
                Automation.trigger_type == "schedule",
                Automation.next_run_at.is_not(None),
                Automation.next_run_at <= now,
            )
        ):
            assert a.next_run_at is not None
            due.append(
                (
                    a.id,
                    "schedule",
                    {"scheduled_for": a.next_run_at.isoformat()},
                    f"{a.id}:sched:{a.next_run_at.isoformat()}",
                )
            )
            a.next_run_at = compute_next_run(db, current_definition(db, a).get("trigger", {}), after=now)
        for a in db.scalars(
            select(Automation).where(Automation.enabled.is_(True), Automation.trigger_type == "deadline_approaching")
        ):
            cfg = current_definition(db, a).get("trigger", {}).get("config", {})
            q = select(Task).where(
                Task.status != "done",
                Task.archived_at.is_(None),
                Task.due_at >= now,
                Task.due_at <= now + timedelta(hours=int(cfg.get("hours", 24))),
            )
            if cfg.get("project_id"):
                q = q.where(Task.project_id == cfg["project_id"])
            for t in db.scalars(q.limit(20)):
                assert t.due_at is not None
                due.append(
                    (
                        a.id,
                        "deadline_approaching",
                        {"task_id": t.id, "title": t.title, "project_id": t.project_id, "due_at": t.due_at.isoformat()},
                        f"{a.id}:deadline:{t.id}:{t.due_at.isoformat()}",
                    )
                )
    for aid, trig, payload, key in due:
        rid = execute(aid, trig, payload, idempotency_key=key)
        if rid:
            runs.append(rid)
    try:
        runs += poll_github()
    except Exception:
        log.exception("Falha ao verificar gatilhos GitHub")
    return runs
