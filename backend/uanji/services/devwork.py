"""Integração com desenvolvimento: código ↔ tarefas ↔ versões.

As tarefas têm um número curto; uma referência **UJ-41** (ou ``uj-41`` num nome de branch)
num commit, branch, pull request ou issue liga essa alteração à tarefa 41. Os repositórios
de cada projecto vêm dos links do projecto: GitHub (``https://github.com/dono/repo``) ou
pasta local com Git (link do tipo «pasta»).
"""

from __future__ import annotations

import re
import shutil
import subprocess  # noqa: S404 (comandos git fixos, sem shell)
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas
from ..errors import AppError, NotFound, ValidationFailed
from ..models import CodeLink, Goal, Project, ProjectLink, ProjectVersion, Task, utcnow
from .common import get_or_404, log_activity
from .performance import goal_progress

REF_RE = re.compile(r"\bUJ-(\d{1,6})\b", re.IGNORECASE)


def task_ref(t: Task) -> str:
    return f"UJ-{t.number}" if t.number else ""


def refs_in(*texts: str) -> set[int]:
    out: set[int] = set()
    for t in texts:
        out |= {int(n) for n in REF_RE.findall(t or "")}
    return out


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


# --------------------------------------------------------------------------- Repositórios do projecto


def project_repos(db: Session, project_id: str) -> list[dict[str, str]]:
    links = db.scalars(select(ProjectLink).where(ProjectLink.project_id == project_id))
    repos = []
    for link in links:
        if link.kind == "github" or "github.com/" in link.url:
            repos.append({"kind": "github", "url": link.url.rstrip("/"), "title": link.title or link.url})
        elif link.kind == "folder":
            repos.append({"kind": "local", "url": link.url, "title": link.title or Path(link.url).name})
    return repos


def _git(path: str, *args: str) -> str:
    git = shutil.which("git")
    if not git:
        return ""
    try:
        return subprocess.run(  # noqa: S603
            [git, "-C", path, *args], capture_output=True, text=True, timeout=8, check=False
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def local_activity(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not (p / ".git").exists():
        raise ValidationFailed(f"A pasta {p} não é um repositório Git.")
    log = _git(str(p), "log", "-40", "--no-merges", "--pretty=%h%x09%an%x09%aI%x09%s")
    commits = []
    for line in log.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append({"sha": parts[0], "author": parts[1], "date": parts[2], "message": parts[3], "url": ""})
    branches = [
        {"name": b.strip().lstrip("* ").strip(), "sha": ""}
        for b in _git(str(p), "branch", "--format=%(refname:short)").splitlines()
        if b.strip()
    ]
    tags = [
        {"tag": t.strip(), "name": t.strip(), "date": None, "url": ""}
        for t in _git(str(p), "tag", "--sort=-creatordate").splitlines()[:10]
        if t.strip()
    ]
    return {
        "repo": p.name,
        "url": str(p),
        "commits": commits,
        "branches": branches,
        "pulls": [],
        "issues": [],
        "releases": tags,
    }


def repo_activity(db: Session, repo: dict[str, str]) -> dict[str, Any]:
    if repo["kind"] == "github":
        from ..integrations.github import GitHubAdapter

        return GitHubAdapter().repo_activity(db, repo["url"])
    return local_activity(repo["url"])


# --------------------------------------------------------------------------- Ligações código → tarefas


def _upsert(db: Session, tasks: dict[int, Task], numbers: set[int], **fields: Any) -> int:
    n = 0
    for num in numbers:
        t = tasks.get(num)
        if t is None:
            continue
        existing = db.scalar(
            select(CodeLink).where(
                CodeLink.task_id == t.id,
                CodeLink.kind == fields["kind"],
                CodeLink.repo == fields["repo"],
                CodeLink.ref == fields["ref"],
            )
        )
        if existing is None:
            db.add(CodeLink(task_id=t.id, **fields))
            n += 1
        else:
            existing.state = fields.get("state", existing.state)
            existing.title = fields.get("title", existing.title)
    return n


def sync_project(db: Session, project_id: str) -> dict[str, Any]:
    """Lê os repositórios do projecto e liga commits, branches, PRs e issues às tarefas referidas (UJ-n)."""
    project = get_or_404(db, Project, project_id)
    repos = project_repos(db, project_id)
    if not repos:
        raise ValidationFailed("O projecto não tem repositórios. Adicione um link GitHub ou uma pasta local com Git.")
    tasks = {t.number: t for t in db.scalars(select(Task).where(Task.number.is_not(None))) if t.number}
    created, errors, scanned = 0, [], []
    for repo in repos:
        try:
            act = repo_activity(db, repo)
        except AppError as e:
            errors.append(f"{repo['title']}: {e.message}")
            continue
        name = act["repo"]
        for c in act["commits"]:
            created += _upsert(
                db,
                tasks,
                refs_in(c["message"]),
                kind="commit",
                repo=name,
                ref=c["sha"],
                title=c["message"][:500],
                url=c.get("url") or "",
                author=c.get("author") or "",
                happened_at=_parse_dt(c.get("date")),
            )
        for b in act["branches"]:
            created += _upsert(
                db,
                tasks,
                refs_in(b["name"].replace("/", " ")),
                kind="branch",
                repo=name,
                ref=b["name"],
                title=b["name"],
                url="",
                state="",
            )
        for p in act["pulls"]:
            created += _upsert(
                db,
                tasks,
                refs_in(p["title"], p.get("body", ""), p.get("branch", "").replace("/", " ")),
                kind="pr",
                repo=name,
                ref=str(p["number"]),
                title=p["title"][:500],
                url=p["url"],
                state=p.get("state") or "",
                author=p.get("author") or "",
                happened_at=_parse_dt(p.get("date")),
            )
        for i in act["issues"]:
            created += _upsert(
                db,
                tasks,
                refs_in(i["title"], i.get("body", "")),
                kind="issue",
                repo=name,
                ref=str(i["number"]),
                title=i["title"][:500],
                url=i["url"],
                state=i.get("state") or "",
                author=i.get("author") or "",
                happened_at=_parse_dt(i.get("date")),
            )
        scanned.append(name)
    log_activity(db, "project", project.id, "code_sync", f"Código sincronizado: {created} ligação(ões) nova(s)")
    return {"repos": scanned, "new_links": created, "errors": errors}


def link_out(link: CodeLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "task_id": link.task_id,
        "kind": link.kind,
        "repo": link.repo,
        "ref": link.ref,
        "title": link.title,
        "url": link.url,
        "state": link.state,
        "author": link.author,
        "happened_at": link.happened_at.isoformat() if link.happened_at else None,
    }


def task_code(db: Session, task_id: str) -> dict[str, Any]:
    t = get_or_404(db, Task, task_id)
    links = db.scalars(select(CodeLink).where(CodeLink.task_id == t.id).order_by(CodeLink.happened_at.desc()))
    return {"ref": task_ref(t), "links": [link_out(link) for link in links]}


def project_code(db: Session, project_id: str) -> dict[str, Any]:
    """Actividade dos repositórios do projecto, com a tarefa ligada a cada item (quando existe)."""
    get_or_404(db, Project, project_id)
    tasks = {t.number: t for t in db.scalars(select(Task).where(Task.project_id == project_id)) if t.number}
    by_num = {n: {"id": t.id, "ref": task_ref(t), "title": t.title, "status": t.status} for n, t in tasks.items()}
    out: list[dict[str, Any]] = []
    for repo in project_repos(db, project_id):
        try:
            act = repo_activity(db, repo)
        except AppError as e:
            out.append({"repo": repo["title"], "url": repo["url"], "error": e.message})
            continue

        def tag(texts: list[str]) -> list[dict[str, Any]]:
            return [by_num[n] for n in sorted(refs_in(*texts)) if n in by_num]

        act["commits"] = [{**c, "tasks": tag([c["message"]])} for c in act["commits"]]
        act["branches"] = [{**b, "tasks": tag([b["name"].replace("/", " ")])} for b in act["branches"]]
        act["pulls"] = [{**p, "tasks": tag([p["title"], p.get("body", ""), p.get("branch", "")])} for p in act["pulls"]]
        act["issues"] = [{**i, "tasks": tag([i["title"], i.get("body", "")])} for i in act["issues"]]
        out.append(act)
    return {"repos": out, "ref_hint": "Escreva UJ-<número> no commit, branch ou PR para ligar à tarefa."}


# --------------------------------------------------------------------------- Objectivos


def list_goals(db: Session, project_id: str | None = None) -> list[dict[str, Any]]:
    q = select(Goal).order_by(Goal.status, Goal.target_date)
    if project_id:
        q = q.where(Goal.project_id == project_id)
    return [goal_progress(db, g) for g in db.scalars(q)]


def save_goal(db: Session, data: schemas.GoalIn, goal_id: str | None = None) -> dict[str, Any]:
    if data.project_id:
        get_or_404(db, Project, data.project_id)
    g = get_or_404(db, Goal, goal_id) if goal_id else Goal()
    for k, v in data.model_dump().items():
        setattr(g, k, v)
    if goal_id is None:
        db.add(g)
    db.flush()
    log_activity(db, "goal", g.id, "saved", f"Objectivo: {g.title}")
    return goal_progress(db, g)


def delete_goal(db: Session, goal_id: str) -> None:
    g = get_or_404(db, Goal, goal_id)
    db.delete(g)


# --------------------------------------------------------------------------- Versões


def version_out(db: Session, v: ProjectVersion) -> dict[str, Any]:
    total = db.scalar(select(func.count(Task.id)).where(Task.version_id == v.id, Task.archived_at.is_(None))) or 0
    done = db.scalar(select(func.count(Task.id)).where(Task.version_id == v.id, Task.status == "done")) or 0
    commits = (
        db.scalar(
            select(func.count(CodeLink.id)).join(Task, Task.id == CodeLink.task_id).where(Task.version_id == v.id)
        )
        or 0
    )
    return {
        "id": v.id,
        "project_id": v.project_id,
        "name": v.name,
        "description": v.description,
        "target_date": v.target_date.isoformat() if v.target_date else None,
        "status": v.status,
        "released_at": v.released_at.isoformat() if v.released_at else None,
        "git_tag": v.git_tag,
        "tasks_total": total,
        "tasks_done": done,
        "percent": round(100 * done / total) if total else None,
        "code_links": commits,
    }


def list_versions(db: Session, project_id: str) -> list[dict[str, Any]]:
    get_or_404(db, Project, project_id)
    vs = db.scalars(
        select(ProjectVersion).where(ProjectVersion.project_id == project_id).order_by(ProjectVersion.created_at)
    )
    return [version_out(db, v) for v in vs]


def save_version(
    db: Session, project_id: str, data: schemas.VersionIn, version_id: str | None = None
) -> dict[str, Any]:
    get_or_404(db, Project, project_id)
    v = get_or_404(db, ProjectVersion, version_id) if version_id else ProjectVersion(project_id=project_id)
    clash = db.scalar(
        select(ProjectVersion.id).where(
            ProjectVersion.project_id == project_id,
            ProjectVersion.name == data.name,
            ProjectVersion.id != (version_id or ""),
        )
    )
    if clash:
        raise ValidationFailed(f"Já existe a versão {data.name} neste projecto.")
    was_released = v.status == "released"
    for k, val in data.model_dump().items():
        setattr(v, k, val)
    if v.status == "released" and not was_released:
        v.released_at = utcnow()
    if version_id is None:
        db.add(v)
    db.flush()
    log_activity(db, "project", project_id, "version", f"Versão {v.name}: {v.status}")
    return version_out(db, v)


def delete_version(db: Session, version_id: str) -> None:
    v = db.get(ProjectVersion, version_id)
    if v is None:
        raise NotFound("Versão não encontrada.")
    db.delete(v)
