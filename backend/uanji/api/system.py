"""Rotas de dashboard, métricas, pesquisa, comandos, notificações, automações, cofre,
backups, integrações, definições, diagnóstico e assistente."""

from __future__ import annotations

import json
import platform
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from .. import schemas
from ..assistant import conversation, reports
from ..assistant import core as assistant
from ..automation import actions as automation_actions
from ..automation import engine
from ..config import APP_VERSION
from ..db import current_revision, fts5_available, head_revision
from ..errors import ConfirmationRequired, ValidationFailed
from ..integrations.base import registry
from ..integrations.github import GitHubAdapter
from ..models import Activity, Automation, AutomationRun, AutomationVersion
from ..services import backups as bsvc
from ..services import commands, metrics, vault
from ..services import notifications as nsvc
from ..services.common import (
    DEFAULT_SETTINGS,
    get_all_settings,
    get_or_404,
    local_today,
    log_activity,
    put_setting,
    search,
    search_engine_name,
)
from .deps import DB

router = APIRouter()


class VoiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listening: bool = False
    wake_word: str = Field(default="UAJI", min_length=2, max_length=30, pattern=r"^[\w\s-]+$")
    sensitivity: float = Field(default=1.0, ge=0.5, le=2.0)
    greeting: str = Field(default="Estou aqui. Em que posso ajudar?", max_length=200)
    tts_enabled: bool = True
    voice: str = Field(default="Joana", max_length=100)
    rate: int = Field(default=185, ge=90, le=360)
    volume: float = Field(default=0.9, ge=0.0, le=1.0)
    language: str = Field(default="pt-PT", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    follow_up_seconds: int = Field(default=8, ge=0, le=30)


class PersonaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: Literal["masculine", "feminine", "neutral", "custom"] = "neutral"
    custom: str = Field(default="", max_length=60)


class AssistantSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["none", "anthropic", "openai_compatible"] = "none"
    model: str = Field(default="", max_length=100)
    base_url: str = Field(default="", max_length=300)
    secret_id: str | None = None
    confirm_creates: bool = False
    confirm_updates: bool = True
    history_days: int = Field(default=30, ge=0, le=3650)
    context_turns: int = Field(default=12, ge=1, le=40)


class ActivitySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    sample_seconds: int = Field(default=15, ge=5, le=120)
    idle_seconds: int = Field(default=300, ge=60, le=3600)
    capture_titles: bool = False
    excluded_apps: list[str] = Field(default_factory=list, max_length=100)
    retention_days: int = Field(default=30, ge=0, le=365)
    git_folders: list[str] = Field(default_factory=list, max_length=20)


class ProactiveSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    voice: bool = True
    intensity: Literal["low", "normal", "high"] = "normal"
    rules: dict[str, bool] = Field(default_factory=dict)


class SystemSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_apps: bool = True
    confirm_system: bool = False
    allow_shell: bool = False


class CardLayout(BaseModel):
    id: str = Field(max_length=40)
    size: Literal["s", "m", "l", "xl"] = "m"
    hidden: bool = False


class AppearanceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["uanji-dark", "abyss", "amber", "contrast", "light"] = "uanji-dark"
    accent: Literal["cyan", "blue", "amber", "emerald", "violet"] = "cyan"
    density: Literal["comfortable", "compact"] = "comfortable"
    font_scale: int = Field(default=100, ge=85, le=130)
    sidebar: Literal["left", "right"] = "left"
    layout_mode: Literal["custom", "adaptive"] = "custom"
    cards: list[CardLayout] = Field(default_factory=list, max_length=30)


SETTING_MODELS: dict[str, type[BaseModel]] = {
    "activity": ActivitySettings,
    "proactive": ProactiveSettings,
    "system": SystemSettings,
    "appearance": AppearanceSettings,
    "voice": VoiceSettings,
    "persona": PersonaSettings,
    "assistant": AssistantSettings,
}

ROUTE_FOR = {
    "project": "/projects/{id}",
    "task": "/tasks/{id}",
    "note": "/notes/{id}",
    "event": "/agenda?event={id}",
    "checklist": "/templates/{id}",
    "automation": "/automations/{id}",
}


# --------------------------------------------------------------------------- Dashboard e métricas


@router.get("/dashboard", tags=["dashboard"])
def dashboard(db: DB) -> dict[str, Any]:
    d = metrics.dashboard(db)
    d["recent_activity"] = [schemas.ActivityOut.model_validate(a) for a in d["recent_activity"]]
    d["focus_active"] = schemas.FocusOut.model_validate(d["focus_active"]) if d["focus_active"] else None
    return d


@router.get("/metrics", tags=["dashboard"])
def get_metrics(db: DB, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    end = end or local_today(db)
    start = start or end - timedelta(days=29)
    return metrics.metrics(db, start, end)


@router.get("/search", response_model=schemas.SearchResult, tags=["search"])
def global_search(
    db: DB,
    q: str = Query(min_length=1, max_length=200),
    types: list[str] | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
) -> schemas.SearchResult:
    hits = search(db, q, types, limit)
    return schemas.SearchResult(
        engine=search_engine_name(db),
        query=q,
        hits=[
            schemas.SearchHit(
                entity_type=h["entity_type"],
                entity_id=h["entity_id"],
                title=h["title"],
                snippet=h["snippet"] or "",
                route=ROUTE_FOR.get(h["entity_type"], "/").format(id=h["entity_id"]),
            )
            for h in hits
        ],
    )


class CommandIn(BaseModel):
    text: str = Field(max_length=1000)


@router.post("/commands", tags=["commands"])
def run_command(db: DB, body: CommandIn) -> dict[str, Any]:
    out = commands.run(db, body.text)
    if out.get("hits"):
        out["hits"] = [
            {**h, "route": ROUTE_FOR.get(h["entity_type"], "/").format(id=h["entity_id"])} for h in out["hits"]
        ]
    return out


@router.get("/commands/suggestions", tags=["commands"])
def command_suggestions() -> list[dict[str, str]]:
    return commands.SUGGESTIONS


@router.get("/activity", response_model=list[schemas.ActivityOut], tags=["history"])
def activity(
    db: DB,
    entity_type: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[schemas.ActivityOut]:
    stmt = select(Activity)
    if entity_type:
        stmt = stmt.where(Activity.entity_type == entity_type)
    if action:
        stmt = stmt.where(Activity.action == action)
    rows = db.scalars(stmt.order_by(Activity.created_at.desc()).limit(limit).offset(offset))
    return [schemas.ActivityOut.model_validate(a) for a in rows]


# --------------------------------------------------------------------------- Notificações


class IdsBody(BaseModel):
    ids: list[str] | None = None


@router.get("/notifications", response_model=list[schemas.NotificationOut], tags=["notifications"])
def list_notifications(db: DB, unread_only: bool = False) -> list[schemas.NotificationOut]:
    return [schemas.NotificationOut.model_validate(n) for n in nsvc.list_notifications(db, unread_only)]


@router.get("/notifications/summary", tags=["notifications"])
def notifications_summary(db: DB) -> dict[str, int]:
    return {"unread": nsvc.unread_count(db)}


@router.post("/notifications/read", tags=["notifications"])
def mark_read(db: DB, body: IdsBody) -> dict[str, int]:
    return {"updated": nsvc.mark_read(db, body.ids)}


@router.get("/notifications/native", response_model=list[schemas.NotificationOut], tags=["notifications"])
def native_pending(db: DB) -> list[schemas.NotificationOut]:
    """Para a camada desktop: notificações a mostrar no centro de notificações do macOS."""
    return [schemas.NotificationOut.model_validate(n) for n in nsvc.pending_native(db)]


@router.post("/notifications/native/sent", tags=["notifications"])
def native_sent(db: DB, body: IdsBody) -> dict[str, bool]:
    nsvc.mark_native_sent(db, body.ids or [])
    return {"ok": True}


# --------------------------------------------------------------------------- Automações


class AutomationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    definition: dict[str, Any]
    enabled: bool = False


class AutomationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    definition: dict[str, Any] | None = None
    enabled: bool | None = None


def _automation_out(db: Any, a: Automation) -> dict[str, Any]:
    last = db.scalars(
        select(AutomationRun).where(AutomationRun.automation_id == a.id).order_by(AutomationRun.started_at.desc())
    ).first()
    counts = dict(
        db.execute(
            select(AutomationRun.status, func.count(AutomationRun.id))
            .where(AutomationRun.automation_id == a.id)
            .group_by(AutomationRun.status)
        ).all()
    )
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "enabled": a.enabled,
        "version": a.current_version,
        "trigger_type": a.trigger_type,
        "last_run_at": a.last_run_at,
        "next_run_at": a.next_run_at,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
        "definition": engine.current_definition(db, a),
        "last_run": _run_out(last, steps=False) if last else None,
        "run_counts": counts,
    }


def _run_out(r: AutomationRun, steps: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": r.id,
        "automation_id": r.automation_id,
        "version": r.version,
        "trigger": r.trigger,
        "status": r.status,
        "error": r.error,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "duration_ms": r.duration_ms,
        "cancel_requested": r.cancel_requested,
    }
    if steps:
        out["context"] = r.context
        out["steps"] = [
            {
                "index": s.index,
                "node_id": s.node_id,
                "action": s.action,
                "status": s.status,
                "attempts": s.attempts,
                "input": s.input,
                "output": s.output,
                "error": s.error,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
            }
            for s in r.steps
        ]
    return out


@router.get("/automations/actions", tags=["automations"])
def action_catalog() -> list[dict[str, Any]]:
    return automation_actions.catalog()


@router.post("/automations/validate", tags=["automations"])
def validate_automation(body: dict[str, Any]) -> dict[str, Any]:
    d, errors = engine.validate_definition(body)
    return {"valid": d is not None, "errors": errors}


@router.get("/automations", tags=["automations"])
def list_automations(db: DB) -> list[dict[str, Any]]:
    return [_automation_out(db, a) for a in db.scalars(select(Automation).order_by(Automation.name))]


@router.post("/automations", status_code=201, tags=["automations"])
def create_automation(db: DB, body: AutomationIn) -> dict[str, Any]:
    a = engine.create_automation(db, body.name, body.description, body.definition, body.enabled)
    return _automation_out(db, a)


@router.get("/automations/{automation_id}", tags=["automations"])
def get_automation(db: DB, automation_id: str) -> dict[str, Any]:
    return _automation_out(db, get_or_404(db, Automation, automation_id))


@router.patch("/automations/{automation_id}", tags=["automations"])
def update_automation(db: DB, automation_id: str, body: AutomationPatch) -> dict[str, Any]:
    a = engine.update_automation(
        db,
        automation_id,
        name=body.name,
        description=body.description,
        definition=body.definition,
        enabled=body.enabled,
    )
    return _automation_out(db, a)


@router.delete("/automations/{automation_id}", status_code=204, tags=["automations"])
def delete_automation(db: DB, automation_id: str, confirm: bool = False) -> None:
    engine.delete_automation(db, automation_id, confirm)


@router.get("/automations/{automation_id}/versions", tags=["automations"])
def automation_versions(db: DB, automation_id: str) -> list[dict[str, Any]]:
    get_or_404(db, Automation, automation_id)
    rows = db.scalars(
        select(AutomationVersion)
        .where(AutomationVersion.automation_id == automation_id)
        .order_by(AutomationVersion.version.desc())
    )
    return [{"version": v.version, "created_at": v.created_at, "definition": v.definition} for v in rows]


class RollbackBody(BaseModel):
    version: int = Field(ge=1)


@router.post("/automations/{automation_id}/rollback", tags=["automations"])
def rollback(db: DB, automation_id: str, body: RollbackBody) -> dict[str, Any]:
    return _automation_out(db, engine.rollback_version(db, automation_id, body.version))


@router.post("/automations/{automation_id}/webhook", tags=["automations"])
def automation_webhook_secret(db: DB, automation_id: str, request: Request) -> dict[str, Any]:
    """Gera um novo segredo para o webhook. O segredo só é mostrado agora; o anterior deixa de valer."""
    secret = engine.create_webhook_secret(db, automation_id)
    base = str(request.base_url).rstrip("/")
    return {
        "url": f"{base}/hooks/{automation_id}",
        "secret": secret,
        "header": "X-UANJI-Secret",
        "example": f"curl -X POST {base}/hooks/{automation_id} -H 'X-UANJI-Secret: {secret}' "
        "-H 'Content-Type: application/json' -d '{\"title\": \"Olá\"}'",
    }


@router.post("/automations/{automation_id}/run", tags=["automations"])
def run_automation(automation_id: str) -> dict[str, Any]:
    """Execução manual. O motor gere as suas próprias transacções (uma por etapa)."""
    from .. import runtime

    run_id = engine.execute(automation_id, "manual", {"source": "manual"})
    with runtime.get_database().session() as db:
        r = get_or_404(db, AutomationRun, run_id) if run_id else None
        return _run_out(r) if r else {"status": "skipped"}


@router.get("/automations/{automation_id}/runs", tags=["automations"])
def automation_runs(db: DB, automation_id: str, limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AutomationRun)
        .where(AutomationRun.automation_id == automation_id)
        .order_by(AutomationRun.started_at.desc())
        .limit(limit)
    )
    return [_run_out(r, steps=False) for r in rows]


@router.get("/automation-runs/{run_id}", tags=["automations"])
def get_run(db: DB, run_id: str) -> dict[str, Any]:
    return _run_out(get_or_404(db, AutomationRun, run_id))


@router.post("/automation-runs/{run_id}/cancel", tags=["automations"])
def cancel_run(db: DB, run_id: str) -> dict[str, Any]:
    return _run_out(engine.request_cancel(db, run_id), steps=False)


# --------------------------------------------------------------------------- Cofre


class SecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    service: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    value: str = Field(min_length=1, max_length=10000)


class SecretPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    service: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    value: str | None = Field(default=None, max_length=10000)


def _secret_out(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "name": e.name,
        "service": e.service,
        "description": e.description,
        "hint": e.hint,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "last_accessed_at": e.last_accessed_at,
    }


@router.get("/vault/status", tags=["vault"])
def vault_status() -> dict[str, Any]:
    return vault.store().status()


@router.get("/vault", tags=["vault"])
def list_secrets(db: DB) -> list[dict[str, Any]]:
    return [_secret_out(e) for e in vault.list_entries(db)]


@router.post("/vault", status_code=201, tags=["vault"])
def create_secret(db: DB, body: SecretIn) -> dict[str, Any]:
    return _secret_out(vault.create_entry(db, body.name, body.service, body.description, body.value))


@router.patch("/vault/{entry_id}", tags=["vault"])
def update_secret(db: DB, entry_id: str, body: SecretPatch) -> dict[str, Any]:
    return _secret_out(
        vault.update_entry(
            db, entry_id, name=body.name, service=body.service, description=body.description, value=body.value
        )
    )


@router.post("/vault/{entry_id}/reveal", tags=["vault"])
def reveal_secret(db: DB, entry_id: str) -> JSONResponse:
    value = vault.reveal(db, entry_id)
    return JSONResponse({"value": value}, headers={"Cache-Control": "no-store"})


@router.delete("/vault/{entry_id}", status_code=204, tags=["vault"])
def delete_secret(db: DB, entry_id: str, confirm: bool = False) -> None:
    vault.delete_entry(db, entry_id, confirm)


# --------------------------------------------------------------------------- Backups

MAX_UPLOAD = 500 * 1024 * 1024


@router.get("/backups", tags=["backups"])
def list_backups(db: DB) -> dict[str, Any]:
    from .. import runtime

    s = runtime.get_settings()
    return {
        "directory": str(s.backups_dir),
        "items": bsvc.list_backups(db, s.backups_dir),
        "automatic": get_all_settings(db)["backups"],
    }


@router.post("/backups", status_code=201, tags=["backups"])
def create_backup() -> dict[str, Any]:
    from .. import runtime

    b = bsvc.create_backup(runtime.get_database(), runtime.get_settings().backups_dir, "manual")
    return {
        "id": b.id,
        "filename": b.filename,
        "size_bytes": b.size_bytes,
        "sha256": b.sha256,
        "created_at": b.created_at,
    }


@router.post("/backups/{filename}/verify", tags=["backups"])
def verify_backup(filename: str) -> dict[str, Any]:
    from .. import runtime

    return bsvc.verify_backup(runtime.get_database(), runtime.get_settings().backups_dir, filename)


@router.post("/backups/{filename}/test-restore", tags=["backups"])
def test_restore(filename: str) -> dict[str, Any]:
    from .. import runtime

    return bsvc.test_restore(runtime.get_settings().backups_dir, filename)


@router.post("/backups/{filename}/restore", tags=["backups"])
def restore_backup(filename: str, body: schemas.ConfirmBody) -> dict[str, Any]:
    from .. import runtime

    s = runtime.get_settings()
    path = bsvc._safe_path(s.backups_dir, filename)
    if not path.exists():
        raise ValidationFailed("Ficheiro de backup não encontrado.")
    return bsvc.restore(runtime.get_database(), s.backups_dir, path, body.confirm)


@router.post("/backups/import", tags=["backups"])
async def import_backup(file: UploadFile = File(...), confirm: bool = False) -> dict[str, Any]:
    """Importa um ficheiro de backup externo. Sem ``confirm`` apenas o valida."""
    from .. import runtime

    s = runtime.get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "upload.zip"
        size = 0
        with dest.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise ValidationFailed("Ficheiro demasiado grande.")
                f.write(chunk)
        if not confirm:
            return {"validated": True, **bsvc.inspect_file(dest)}
        return bsvc.restore(runtime.get_database(), s.backups_dir, dest, True)


@router.get("/backups/{filename}/download", tags=["backups"])
def download_backup(filename: str) -> FileResponse:
    from .. import runtime

    path = bsvc._safe_path(runtime.get_settings().backups_dir, filename)
    if not path.exists():
        raise ValidationFailed("Ficheiro de backup não encontrado.")
    return FileResponse(path, filename=filename, media_type="application/zip")


@router.get("/export", tags=["backups"])
def export_data(db: DB) -> JSONResponse:
    data = bsvc.export_json(db)
    log_activity(db, "backup", "export", "exported", "Exportação JSON dos dados")
    return JSONResponse(
        json.loads(json.dumps(data, default=str)),
        headers={"Content-Disposition": 'attachment; filename="uanji-export.json"'},
    )


# --------------------------------------------------------------------------- Integrações


class IntegrationConfig(BaseModel):
    secret_id: str | None = None


class RepoQuery(BaseModel):
    url: str = Field(min_length=10, max_length=500)


@router.get("/integrations", tags=["integrations"])
def list_integrations(db: DB) -> list[dict[str, Any]]:
    return [a.status(db) for a in registry().values()]


@router.put("/integrations/{provider}", tags=["integrations"])
def configure_integration(db: DB, provider: str, body: IntegrationConfig) -> dict[str, Any]:
    adapters = registry()
    if provider not in adapters:
        raise ValidationFailed("Integração desconhecida.")
    return adapters[provider].configure(db, body.secret_id)


@router.post("/integrations/{provider}/test", tags=["integrations"])
def test_integration(db: DB, provider: str) -> dict[str, Any]:
    adapters = registry()
    if provider not in adapters:
        raise ValidationFailed("Integração desconhecida.")
    return adapters[provider].test(db)


@router.post("/integrations/github/repo", tags=["integrations"])
def github_repo(db: DB, body: RepoQuery) -> dict[str, Any]:
    return GitHubAdapter().repo_overview(db, body.url)


# --------------------------------------------------------------------------- Definições e diagnóstico


@router.get("/settings", tags=["settings"])
def get_settings_route(db: DB) -> dict[str, Any]:
    return get_all_settings(db)


@router.patch("/settings", tags=["settings"])
def patch_settings(db: DB, body: schemas.SettingsPatch) -> dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS)
    for key, value in body.values.items():
        if key not in allowed:
            raise ValidationFailed(f"Definição desconhecida: {key}")
        if key == "timezone":
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(str(value))
            except (ZoneInfoNotFoundError, ValueError) as e:
                raise ValidationFailed("Fuso horário inválido.") from e
        if isinstance(DEFAULT_SETTINGS[key], dict) and not isinstance(value, dict):
            raise ValidationFailed(f"Valor inválido para {key}.")
        current = get_all_settings(db)[key]
        merged = {**current, **value} if isinstance(current, dict) else value
        if key == "assistant" and merged.get("provider") == "openai_compatible" and merged.get("base_url"):
            from ..assistant.openai_compat import check_base_url

            merged["base_url"] = check_base_url(str(merged["base_url"]))
        if key in SETTING_MODELS:
            try:
                merged = SETTING_MODELS[key].model_validate(merged).model_dump()
            except ValidationError as e:
                first = e.errors()[0]
                raise ValidationFailed(f"Valor inválido em {key}.{first['loc'][0]}: {first['msg']}") from e
        put_setting(db, key, merged)
    log_activity(db, "settings", "settings", "updated", f"Definições alteradas: {', '.join(body.values)}")
    db.flush()
    result = get_all_settings(db)
    if {"voice", "persona", "proactive"} & set(body.values):
        from ..voice import service as voice_service

        db.commit()
        voice_service.get().apply_settings(result)
    if "activity" in body.values:
        from ..activity import monitor as activity_monitor

        db.commit()
        activity_monitor.apply_settings(result["activity"])
    return result


@router.get("/diagnostics", tags=["settings"])
def diagnostics(db: DB) -> dict[str, Any]:
    from .. import runtime

    s = runtime.get_settings()
    database = runtime.get_database()
    usage = shutil.disk_usage(s.data_dir)
    log_file = s.logs_dir / "backend.log"
    return {
        "app_version": APP_VERSION,
        "env": s.env,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "data_dir": str(s.data_dir),
        "db_path": str(s.db_path),
        "db_size_bytes": s.db_path.stat().st_size if s.db_path.exists() else 0,
        "schema_revision": current_revision(database.engine),
        "schema_head": head_revision(database.url),
        "search_engine": search_engine_name(db),
        "fts5_available": fts5_available(database.engine),
        "vault": vault.store().status(),
        "assistant": assistant.provider_status(db),
        "disk_free_bytes": usage.free,
        "scheduler_enabled": s.scheduler_enabled,
        "log_file": str(log_file),
    }


class ClientError(BaseModel):
    message: str = Field(max_length=2000)
    stack: str = Field(default="", max_length=8000)
    url: str = Field(default="", max_length=500)
    source: str = Field(default="", max_length=50)


@router.post("/diagnostics/client-error", tags=["settings"])
def client_error(body: ClientError) -> dict[str, bool]:
    """Erros da interface (WebView), registados no log do backend para diagnóstico."""
    import logging

    logging.getLogger("uanji.frontend").error(
        "Erro na interface (%s): %s | %s | %s", body.source, body.message, body.url, body.stack[:4000]
    )
    return {"ok": True}


@router.get("/diagnostics/logs", tags=["settings"])
def logs(lines: int = Query(200, ge=1, le=2000)) -> dict[str, Any]:
    from .. import runtime

    log_file = runtime.get_settings().logs_dir / "backend.log"
    if not log_file.exists():
        return {"lines": []}
    with log_file.open("r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()[-lines:]
    # Os logs já são redigidos na escrita (ver logging_setup.redact).
    return {"lines": [line.rstrip("\n") for line in content]}


# --------------------------------------------------------------------------- Assistente


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=40)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=36)
    speak: bool = False


class ActionDecision(BaseModel):
    approve: bool


@router.get("/assistant/status", tags=["assistant"])
def assistant_status(db: DB) -> dict[str, Any]:
    return assistant.provider_status(db)


@router.post("/assistant/test", tags=["assistant"])
def assistant_test(db: DB) -> dict[str, Any]:
    """Testa a ligação ao fornecedor de IA configurado (Anthropic ou modelo próprio)."""
    return assistant.test_provider(db)


@router.post("/assistant/chat", tags=["assistant"])
def assistant_chat(db: DB, body: ChatIn) -> dict[str, Any]:
    """Conversa directa com o fornecedor de IA (requer fornecedor configurado)."""
    return assistant.chat(db, body.history, body.message)


@router.post("/assistant/message", tags=["assistant"])
def assistant_message(body: MessageIn) -> dict[str, Any]:
    """Ponto de entrada do assistente (texto). Funciona sem IA para os pedidos reconhecidos localmente."""
    from ..voice import service as voice_service

    return voice_service.get().text_turn(body.text, body.conversation_id, speak=body.speak)


@router.post("/assistant/actions/{action_id}", tags=["assistant"])
def assistant_action(action_id: str, body: ActionDecision) -> dict[str, Any]:
    turn = conversation.Assistant().decide(action_id, body.approve)
    a = turn["actions"][0]
    return {**turn, "id": a["id"], "status": a["status"], "summary": a["summary"], "result": a["result"]}


@router.get("/assistant/history", tags=["assistant"])
def assistant_history(
    conversation_id: str | None = None, limit: int = Query(100, ge=1, le=500)
) -> list[dict[str, Any]]:
    return conversation.history(conversation_id, limit)


@router.delete("/assistant/history", tags=["assistant"])
def clear_assistant_history(confirm: bool = False) -> dict[str, int]:
    if not confirm:
        raise ConfirmationRequired("Apagar todo o histórico de conversa? Confirme a operação.")
    return {"deleted": conversation.purge_history(0)}


@router.get("/assistant/reports/{kind}", tags=["assistant"])
def assistant_report(db: DB, kind: str) -> dict[str, Any]:
    if kind not in reports.BUILDERS:
        raise ValidationFailed("Tipo de relatório desconhecido.")
    return reports.build(db, kind).to_dict()
