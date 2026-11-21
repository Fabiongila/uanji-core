"""Backups, verificação, exportação e restauro.

Formato: ficheiro ZIP com ``uanji.db`` (cópia consistente via API de backup do SQLite)
e ``manifest.json`` (versão, revisão do esquema, SHA-256 da base de dados).

Os segredos NÃO são incluídos: a base de dados só contém metadados; os valores ficam
no macOS Keychain do computador onde foram criados.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from ..config import APP_VERSION
from ..db import Database, alembic_config, current_revision, upgrade_to_head
from ..errors import ConfirmationRequired, NotFound, ValidationFailed
from ..models import Backup, utcnow
from .common import get_all_settings, log_activity

log = logging.getLogger(__name__)

FILENAME_RE = re.compile(r"^uanji-backup-\d{8}-\d{6}-[a-z_]+(-\d+)?\.zip$")
MANIFEST = "manifest.json"
DB_NAME = "uanji.db"
COUNT_TABLES = ("projects", "tasks", "notes", "events", "checklists", "automations", "secrets")
_restore_lock = threading.Lock()
KIND_LABELS = {
    "manual": "manual",
    "automatic": "automático",
    "pre_restore": "de segurança (antes de restauro)",
    "pre_migration": "de segurança (antes de migração)",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_path(backups_dir: Path, filename: str) -> Path:
    if not FILENAME_RE.match(filename):
        raise ValidationFailed("Nome de ficheiro de backup inválido.")
    p = (backups_dir / filename).resolve()
    if p.parent != backups_dir.resolve():
        raise ValidationFailed("Caminho de backup inválido.")
    return p


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for t in COUNT_TABLES:
        try:
            out[t] = int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])  # noqa: S608 (lista fixa)
        except sqlite3.OperationalError:
            out[t] = 0
    return out


def create_backup(database: Database, backups_dir: Path, kind: str = "manual") -> Backup:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"uanji-backup-{stamp}-{kind}.zip"
    n = 1
    while (backups_dir / filename).exists():
        filename = f"uanji-backup-{stamp}-{kind}-{n}.zip"
        n += 1
    target = backups_dir / filename
    db_path = Path(database.url.removeprefix("sqlite:///"))
    revision = current_revision(database.engine) or ""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / DB_NAME
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(copy)
        try:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()[0]
            counts = _counts(dst)
        finally:
            dst.close()
            src.close()
        if check != "ok":
            raise ValidationFailed(f"A base de dados actual falhou a verificação de integridade: {check}")
        manifest = {
            "format": 1,
            "app": "uanji-core",
            "app_version": APP_VERSION,
            "schema_revision": revision,
            "created_at": utcnow().isoformat(),
            "kind": kind,
            "db_sha256": _sha256(copy),
            "counts": counts,
            "secrets_included": False,
        }
        tmp_zip = Path(tmp) / filename
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(copy, DB_NAME)
            z.writestr(MANIFEST, json.dumps(manifest, indent=2))
        shutil.move(str(tmp_zip), target)
    with database.session() as db:
        b = Backup(
            filename=filename,
            kind=kind,
            size_bytes=target.stat().st_size,
            sha256=_sha256(target),
            schema_revision=revision,
            status="ok",
            verified_at=utcnow(),
        )
        db.add(b)
        db.flush()
        log_activity(db, "backup", b.id, "created", f"Backup {KIND_LABELS.get(kind, kind)} criado: {filename}")
        db.flush()
        db.expunge(b)
    _apply_retention(database, backups_dir)
    return b


def _apply_retention(database: Database, backups_dir: Path) -> None:
    with database.session() as db:
        keep = int(get_all_settings(db)["backups"].get("keep", 10))
        autos = list(db.scalars(select(Backup).where(Backup.kind == "automatic").order_by(Backup.created_at.desc())))
        for b in autos[keep:]:
            with contextlib.suppress(ValidationFailed):
                _safe_path(backups_dir, b.filename).unlink(missing_ok=True)
            db.delete(b)


def inspect_file(path: Path) -> dict[str, Any]:
    """Valida um ficheiro de backup sem o aplicar: estrutura, checksum, integridade, revisão."""
    if not zipfile.is_zipfile(path):
        raise ValidationFailed("O ficheiro não é um backup válido (ZIP).")
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if names != {DB_NAME, MANIFEST}:
            raise ValidationFailed("Conteúdo inesperado no backup.", {"entries": sorted(names)})
        info = z.getinfo(DB_NAME)
        if info.file_size > 2_000_000_000:
            raise ValidationFailed("Backup demasiado grande.")
        try:
            manifest = json.loads(z.read(MANIFEST))
        except json.JSONDecodeError as e:
            raise ValidationFailed("Manifesto inválido.") from e
        if manifest.get("app") != "uanji-core":
            raise ValidationFailed("O ficheiro não foi criado pelo UANJI CORE.")
        with tempfile.TemporaryDirectory() as tmp:
            extracted = Path(tmp) / DB_NAME
            with z.open(DB_NAME) as src, extracted.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            if _sha256(extracted) != manifest.get("db_sha256"):
                raise ValidationFailed("Checksum SHA-256 não corresponde: o backup está corrompido.")
            conn = sqlite3.connect(extracted)
            try:
                check = conn.execute("PRAGMA integrity_check").fetchone()[0]
                rev_row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
                counts = _counts(conn)
            except sqlite3.DatabaseError as e:
                raise ValidationFailed(f"Base de dados ilegível: {e}") from e
            finally:
                conn.close()
    if check != "ok":
        raise ValidationFailed(f"Falha na verificação de integridade: {check}")
    revision = rev_row[0] if rev_row else None
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    known = {r.revision for r in script.walk_revisions()}
    if revision not in known:
        raise ValidationFailed(
            "O backup foi criado por uma versão mais recente ou desconhecida do UANJI CORE.", {"revision": revision}
        )
    return {"manifest": manifest, "schema_revision": revision, "counts": counts, "integrity": "ok"}


def list_backups(db: Session, backups_dir: Path) -> list[dict[str, Any]]:
    out = []
    for b in db.scalars(select(Backup).order_by(Backup.created_at.desc())):
        exists = (backups_dir / b.filename).exists()
        out.append(
            {
                "id": b.id,
                "filename": b.filename,
                "kind": b.kind,
                "size_bytes": b.size_bytes,
                "sha256": b.sha256,
                "schema_revision": b.schema_revision,
                "status": b.status if exists else "missing",
                "error": b.error,
                "verified_at": b.verified_at,
                "created_at": b.created_at,
            }
        )
    return out


def sync_files(database: Database, backups_dir: Path) -> int:
    """Regista ficheiros de backup existentes no disco que não constam da tabela (ex.: após restauro)."""
    added = 0
    if not backups_dir.exists():
        return 0
    with database.session() as db:
        known = set(db.scalars(select(Backup.filename)))
        for f in sorted(backups_dir.glob("uanji-backup-*.zip")):
            if f.name in known or not FILENAME_RE.match(f.name):
                continue
            try:
                info = inspect_file(f)
                status, err = "ok", ""
                rev = str(info["schema_revision"])
                kind = str(info["manifest"].get("kind", "manual"))
                created = datetime.fromisoformat(info["manifest"]["created_at"])
            except ValidationFailed as e:
                status, err, rev, kind, created = "failed", e.message, "", "manual", utcnow()
            db.add(
                Backup(
                    filename=f.name,
                    kind=kind,
                    size_bytes=f.stat().st_size,
                    sha256=_sha256(f),
                    schema_revision=rev,
                    status=status,
                    error=err,
                    created_at=created,
                    verified_at=utcnow() if status == "ok" else None,
                )
            )
            added += 1
    return added


def verify_backup(database: Database, backups_dir: Path, filename: str) -> dict[str, Any]:
    path = _safe_path(backups_dir, filename)
    if not path.exists():
        raise NotFound("Ficheiro de backup não encontrado.")
    with database.session() as db:
        b = db.scalars(select(Backup).where(Backup.filename == filename)).first()
        try:
            info = inspect_file(path)
            if b:
                b.status, b.error, b.verified_at = "ok", "", utcnow()
            return info
        except ValidationFailed as e:
            if b:
                b.status, b.error = "failed", e.message
            raise


def restore(database: Database, backups_dir: Path, source: Path, confirm: bool) -> dict[str, Any]:
    """Substitui a base de dados actual pelo backup, após validação e backup de segurança."""
    info = inspect_file(source)
    if not confirm:
        raise ConfirmationRequired(
            "O restauro substitui TODOS os dados actuais. Será criado um backup de segurança antes.",
            {"backup": info},
        )
    with _restore_lock:
        safety = create_backup(database, backups_dir, kind="pre_restore")
        db_path = Path(database.url.removeprefix("sqlite:///"))
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(source) as z:
                z.extract(DB_NAME, tmp)
            database.dispose()
            for suffix in ("-wal", "-shm"):
                Path(str(db_path) + suffix).unlink(missing_ok=True)
            shutil.copyfile(Path(tmp) / DB_NAME, db_path)
        database.reopen()
        upgrade_to_head(database.url)
        sync_files(database, backups_dir)
        with database.session() as db:
            log_activity(
                db,
                "backup",
                safety.id,
                "restored",
                f"Dados restaurados a partir de {source.name}. Backup de segurança: {safety.filename}",
            )
    return {"restored_from": source.name, "safety_backup": safety.filename, "counts": info["counts"]}


def test_restore(backups_dir: Path, filename: str) -> dict[str, Any]:
    """Restaura o backup numa base de dados temporária, aplica migrações e devolve contagens."""
    path = _safe_path(backups_dir, filename)
    info = inspect_file(path)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as z:
            z.extract(DB_NAME, tmp)
        url = f"sqlite:///{Path(tmp) / DB_NAME}"
        upgrade_to_head(url)
        conn = sqlite3.connect(Path(tmp) / DB_NAME)
        try:
            counts = _counts(conn)
        finally:
            conn.close()
    return {"ok": True, "counts": counts, "manifest": info["manifest"]}


def needs_automatic_backup(db: Session) -> bool:
    cfg = get_all_settings(db)["backups"]
    if not cfg.get("automatic", True):
        return False
    last = db.scalars(select(Backup).where(Backup.status == "ok").order_by(Backup.created_at.desc())).first()
    return last is None or last.created_at < utcnow() - timedelta(hours=int(cfg.get("interval_hours", 24)))


def export_json(db: Session) -> dict[str, Any]:
    """Exportação legível de todos os dados (sem valores de segredos)."""
    insp = inspect(db.get_bind())
    data: dict[str, Any] = {}
    for table in insp.get_table_names():
        if table.startswith("search_index") or table == "alembic_version":
            continue
        rows = db.execute(text(f'SELECT * FROM "{table}"')).mappings().all()  # noqa: S608 (nomes do esquema)
        data[table] = [
            {k: (v.isoformat() if isinstance(v, datetime | date) else v) for k, v in r.items()} for r in rows
        ]
    return {
        "app": "uanji-core",
        "app_version": APP_VERSION,
        "exported_at": utcnow().isoformat(),
        "secrets_included": False,
        "tables": data,
    }
