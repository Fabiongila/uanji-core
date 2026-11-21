"""Rotas do centro de desempenho, objectivos, versões, código e Command Palette."""

from __future__ import annotations

import os
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import schemas
from ..errors import NotFound, ValidationFailed
from ..models import ProjectLink
from ..services import devwork, performance
from ..services.common import get_all_settings
from .deps import DB

router = APIRouter()


# --------------------------------------------------------------------------- Desempenho e objectivos


@router.get("/performance", tags=["performance"])
def performance_center(db: DB, weeks: int = Query(8, ge=2, le=26), project_id: str | None = None) -> dict[str, Any]:
    return performance.center(db, weeks, project_id)


@router.get("/goals", tags=["performance"])
def goals(db: DB, project_id: str | None = None) -> list[dict[str, Any]]:
    return devwork.list_goals(db, project_id)


@router.post("/goals", status_code=201, tags=["performance"])
def create_goal(db: DB, body: schemas.GoalIn) -> dict[str, Any]:
    return devwork.save_goal(db, body)


@router.put("/goals/{goal_id}", tags=["performance"])
def update_goal(db: DB, goal_id: str, body: schemas.GoalIn) -> dict[str, Any]:
    return devwork.save_goal(db, body, goal_id)


@router.delete("/goals/{goal_id}", status_code=204, tags=["performance"])
def delete_goal(db: DB, goal_id: str) -> None:
    devwork.delete_goal(db, goal_id)


# --------------------------------------------------------------------------- Versões e código


@router.get("/projects/{project_id}/versions", tags=["code"])
def versions(db: DB, project_id: str) -> list[dict[str, Any]]:
    return devwork.list_versions(db, project_id)


@router.post("/projects/{project_id}/versions", status_code=201, tags=["code"])
def create_version(db: DB, project_id: str, body: schemas.VersionIn) -> dict[str, Any]:
    return devwork.save_version(db, project_id, body)


@router.put("/projects/{project_id}/versions/{version_id}", tags=["code"])
def update_version(db: DB, project_id: str, version_id: str, body: schemas.VersionIn) -> dict[str, Any]:
    return devwork.save_version(db, project_id, body, version_id)


@router.delete("/versions/{version_id}", status_code=204, tags=["code"])
def delete_version(db: DB, version_id: str) -> None:
    devwork.delete_version(db, version_id)


@router.get("/projects/{project_id}/code", tags=["code"])
def project_code(db: DB, project_id: str) -> dict[str, Any]:
    return devwork.project_code(db, project_id)


@router.post("/projects/{project_id}/code/sync", tags=["code"])
def sync_code(db: DB, project_id: str) -> dict[str, Any]:
    return devwork.sync_project(db, project_id)


@router.get("/tasks/{task_id}/code", tags=["code"])
def task_code(db: DB, task_id: str) -> dict[str, Any]:
    return devwork.task_code(db, task_id)


# --------------------------------------------------------------------------- Command Palette: ficheiros

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    ".next",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "Pods",
    ".dev-data",
    ".dev-data-desktop",
}
MAX_FILES = 40_000
_index: dict[str, tuple[float, list[str]]] = {}
_index_lock = threading.Lock()


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def search_roots(db: Any) -> list[Path]:
    roots: list[Path] = []
    for link in db.scalars(select(ProjectLink).where(ProjectLink.kind == "folder")):
        roots.append(Path(link.url).expanduser())
    for f in get_all_settings(db)["activity"].get("git_folders") or []:
        roots.append(Path(f).expanduser())
    home = Path.home().resolve()
    out = []
    for r in roots:
        try:
            rr = r.resolve()
        except OSError:
            continue
        if rr.is_dir() and rr.is_relative_to(home) and rr not in out:
            out.append(rr)
    return out


def _files(root: Path) -> list[str]:
    key = str(root)
    with _index_lock:
        hit = _index.get(key)
        if hit and time.monotonic() - hit[0] < 120:
            return hit[1]
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if dirpath[len(str(root)) :].count(os.sep) > 7:
            dirnames[:] = []
        for f in filenames:
            if not f.startswith("."):
                found.append(os.path.join(dirpath, f))
        if len(found) >= MAX_FILES:
            break
    with _index_lock:
        _index[key] = (time.monotonic(), found)
    return found


@router.get("/palette/files", tags=["palette"])
def palette_files(
    db: DB, q: str = Query(min_length=1, max_length=120), limit: int = Query(12, ge=1, le=50)
) -> dict[str, Any]:
    """Procura ficheiros por nome nas pastas dos projectos (links «pasta») e nas pastas de código das Definições."""
    roots = search_roots(db)
    if not roots:
        return {
            "roots": [],
            "files": [],
            "hint": "Adicione uma pasta local a um projecto (link do tipo «pasta») "
            "ou indique pastas de projectos em Actividade.",
        }
    terms = [t for t in _fold(q).split() if t]
    scored: list[tuple[int, str, Path]] = []
    for root in roots:
        for path in _files(root):
            rel = path[len(str(root)) + 1 :]
            name = _fold(os.path.basename(path))
            low = _fold(rel)
            if all(t in low for t in terms):
                score = (0 if name.startswith(terms[0]) else 1 if terms[0] in name else 2) * 1000 + len(rel)
                scored.append((score, rel, root))
    scored.sort()
    return {
        "roots": [str(r) for r in roots],
        "files": [{"path": str(root / rel), "relative": rel, "root": root.name} for _, rel, root in scored[:limit]],
    }


class OpenFileIn(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    editor: bool = True


@router.post("/palette/open-file", tags=["palette"])
def open_file(db: DB, body: OpenFileIn) -> dict[str, str]:
    """Abre o ficheiro no VS Code (se instalado) ou na aplicação por omissão. Só dentro das pastas indicadas."""
    from ..system import macos

    p = Path(body.path).expanduser().resolve()
    if not any(p.is_relative_to(r) for r in search_roots(db)):
        raise ValidationFailed("Só abro ficheiros das pastas de projectos configuradas.")
    if not p.exists():
        raise NotFound("O ficheiro já não existe.")
    app = macos.find_app("Visual Studio Code") if body.editor else None
    args = ["/usr/bin/open", "-a", str(app), str(p)] if app else ["/usr/bin/open", str(p)]
    r = macos.runner(args)
    if r.code != 0:
        raise ValidationFailed("Não foi possível abrir o ficheiro.")
    return {"opened": str(p), "with": app.stem if app else "aplicação por omissão"}
