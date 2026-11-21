"""Aplicação FastAPI e ponto de entrada do backend local."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import signal
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import events, runtime
from .activity import monitor as activity_monitor
from .api import activity, content, devwork, system, voice, work
from .api.deps import require_token
from .assistant import conversation, proactive
from .automation import engine
from .config import APP_VERSION, Settings, get_settings
from .db import Database, current_revision, head_revision, upgrade_to_head
from .errors import install_error_handlers
from .logging_setup import setup_logging
from .services import backups, notifications, vault
from .services.checklists import seed_builtin_templates
from .voice import service as voice_service

log = logging.getLogger("uanji")


def prepare_database(settings: Settings) -> Database:
    """Cria/migra a base de dados. Faz backup antes de migrar uma base existente."""
    settings.ensure_dirs()
    existed = settings.db_path.exists() and settings.db_path.stat().st_size > 0
    database = Database(settings.database_url)
    if existed:
        cur = current_revision(database.engine)
        head = head_revision(settings.database_url)
        if cur != head and cur is not None:
            log.info("Migração pendente %s → %s; a criar backup de segurança", cur, head)
            backups.create_backup(database, settings.backups_dir, kind="pre_migration")
    upgrade_to_head(settings.database_url)
    database.reopen()
    with database.session() as db:
        seed_builtin_templates(db)
    backups.sync_files(database, settings.backups_dir)
    return database


def scheduler_iteration(settings: Settings) -> None:
    database = runtime.get_database()
    try:
        engine.scheduler_tick()
    except Exception:
        log.exception("Falha no agendador de automações")
    try:
        with database.session() as db:
            notifications.generate_reminders(db)
            needs = backups.needs_automatic_backup(db)
        if needs:
            try:
                backups.create_backup(database, settings.backups_dir, kind="automatic")
            except Exception as e:
                log.exception("Backup automático falhou")
                with database.session() as db:
                    notifications.create(
                        db,
                        category="backup",
                        level="error",
                        title="Backup automático falhou",
                        body=str(e)[:300],
                        link="/backups",
                    )
    except Exception:
        log.exception("Falha na geração de lembretes")
    try:
        activity_monitor.ActivityMonitor.purge()
    except Exception:
        log.exception("Falha ao aplicar a retenção da actividade")
    try:
        conversation.purge_history()
    except Exception:
        log.exception("Falha ao aplicar a retenção do histórico do assistente")


async def _scheduler_loop(settings: Settings) -> None:
    await asyncio.sleep(5)
    while True:
        await asyncio.to_thread(scheduler_iteration, settings)
        await asyncio.sleep(settings.scheduler_interval_seconds)


async def _watch_parent() -> None:
    """Encerra o backend se o processo desktop que o lançou terminar (evita processos órfãos)."""
    parent = os.getppid()
    while True:
        await asyncio.sleep(2)
        if os.getppid() != parent:
            log.info("Processo pai terminou; a encerrar")
            os.kill(os.getpid(), signal.SIGTERM)
            return


def _start_background_services() -> None:
    """Voz (retoma a escuta se estava activa), monitor de actividade (se autorizado) e iniciativa."""
    voice_service.get()
    database = runtime.get_database()
    with database.session() as db:
        from .services.common import get_all_settings

        settings = get_all_settings(db)
    activity_monitor.apply_settings(settings["activity"])
    engine = proactive.ProactiveEngine(deliver=lambda n: voice_service.get().proactive(n))
    proactive.set_engine(engine)
    engine.start()


def create_app(
    settings: Settings | None = None,
    secret_store: vault.SecretStore | None = None,
    watch_parent: bool = False,
) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.logs_dir, settings.log_level)
    if secret_store is None:
        secret_store = (
            vault.MemoryStore()
            if settings.secret_backend == "memory"  # noqa: S105
            else vault.KeychainStore(settings.keychain_service)
        )
    vault.init_store(secret_store)
    database = prepare_database(settings)
    runtime.init(database, settings)
    events.clear_handlers()
    events.subscribe("task.completed", engine.on_task_completed)
    voice_service.set_service(None)
    activity_monitor.set_monitor(None)
    proactive.set_engine(None)
    conversation.reset_contexts()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_scheduler_loop(settings)) if settings.scheduler_enabled else None
        watcher = asyncio.create_task(_watch_parent()) if watch_parent else None
        if settings.env != "test":
            # Retoma a escuta se estava activa (o microfone só abre se a preferência o indicar).
            asyncio.get_running_loop().run_in_executor(None, _start_background_services)
        log.info("UANJI CORE backend %s pronto em %s:%s", APP_VERSION, settings.host, settings.port)
        yield
        for t in (task, watcher):
            if t:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t
        proactive.set_engine(None)
        activity_monitor.set_monitor(None)
        voice_service.set_service(None)
        database.dispose()
        log.info("Backend encerrado")

    app = FastAPI(
        title="UANJI CORE — API local",
        version=APP_VERSION,
        description="API local do UANJI CORE. Todos os pedidos (excepto /health) exigem "
        "`Authorization: Bearer <token>`.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    install_error_handlers(app)

    allowed_hosts = {f"127.0.0.1:{settings.port}", f"localhost:{settings.port}", "127.0.0.1", "localhost", "testserver"}

    @app.middleware("http")
    async def host_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Protecção contra DNS rebinding: só aceitamos o anfitrião local.
        if request.headers.get("host", "") not in allowed_hosts:
            return JSONResponse(
                {"error": {"code": "forbidden", "message": "Anfitrião não permitido."}}, status_code=403
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    @app.post("/hooks/{automation_id}", tags=["automations"])
    async def webhook(automation_id: str, request: Request) -> dict[str, Any]:
        """Gatilho para aplicações externas (só aceita ligações locais e o segredo do webhook)."""
        from .errors import ValidationFailed as _VF

        raw = await request.body()
        if len(raw) > 64_000:
            raise _VF("Corpo do pedido demasiado grande (máximo 64 KB).")
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError as e:
            raise _VF("O corpo tem de ser JSON.") from e
        if not isinstance(payload, dict):
            payload = {"value": payload}
        secret = request.headers.get("x-uanji-secret", "")
        with database.session() as db:
            engine.check_webhook(db, automation_id, secret)
        key = request.headers.get("x-idempotency-key")
        run_id = await asyncio.to_thread(
            engine.execute, automation_id, "webhook", payload, f"{automation_id}:hook:{key}" if key else None
        )
        return {"accepted": True, "run_id": run_id}

    protected = [Depends(require_token)]
    for r in (work.router, content.router, system.router, voice.router, activity.router, devwork.router):
        app.include_router(r, prefix="/api", dependencies=protected)
    return app


def run() -> None:
    """Executado pelo processo desktop: ``python -m uanji`` ou executável empacotado."""
    import uvicorn

    settings = get_settings()
    if "UANJI_TOKEN" not in os.environ:
        print("UANJI_TOKEN não definido: o backend recusa iniciar sem token.", file=sys.stderr)
        sys.exit(2)
    app = create_app(settings, watch_parent=os.environ.get("UANJI_WATCH_PARENT") == "1")
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None, access_log=False)


if __name__ == "__main__":
    run()
