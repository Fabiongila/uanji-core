"""Adaptador GitHub (API REST v3, apenas leitura).

Operações suportadas e validadas:
- Testar ligação (``GET /user``) com um token guardado no cofre.
- Ler metadados de um repositório, últimos commits e pull requests abertos.

Sem token, os repositórios públicos funcionam com o limite anónimo da API (60 pedidos/h).
Os resultados vêm sempre da API; nada é inventado nem guardado como dado próprio.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ExternalServiceError, ValidationFailed
from ..models import Integration, SecretEntry, utcnow
from ..services import vault
from ..services.common import get_or_404, log_activity
from .base import IntegrationAdapter

API = "https://api.github.com"
REPO_RE = re.compile(r"^https?://(www\.)?github\.com/([\w.-]+)/([\w.-]+?)(\.git)?/?$")
CACHE_SECONDS = 300

# Substituível em testes (httpx.MockTransport).
transport: httpx.BaseTransport | None = None
_cache: dict[str, tuple[float, Any]] = {}


def parse_repo(url: str) -> tuple[str, str]:
    m = REPO_RE.match(url.strip())
    if not m:
        raise ValidationFailed("URL de repositório GitHub inválido. Use https://github.com/dono/repositorio")
    return m.group(2), m.group(3)


class GitHubAdapter(IntegrationAdapter):
    provider = "github"
    label = "GitHub"

    def _integration(self, db: Session) -> Integration:
        i = db.scalars(select(Integration).where(Integration.provider == self.provider)).first()
        if i is None:
            i = Integration(provider=self.provider)
            db.add(i)
            db.flush()
        return i

    def _token(self, db: Session) -> str | None:
        i = self._integration(db)
        return vault.read_for_integration(db, i.secret_id) if i.secret_id else None

    def _client(self, token: str | None) -> httpx.Client:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "uanji-core",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.Client(base_url=API, headers=headers, timeout=10.0, transport=transport)

    def _get(self, db: Session, path: str, params: dict[str, Any] | None = None) -> Any:
        key = path + repr(sorted((params or {}).items()))
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        token = self._token(db)
        try:
            with self._client(token) as c:
                r = c.get(path, params=params)
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"Sem ligação ao GitHub: {type(e).__name__}") from e
        if r.status_code == 401:
            raise ExternalServiceError("Token GitHub inválido ou expirado (401).")
        if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
            raise ExternalServiceError("Limite de pedidos da API GitHub atingido. Configure um token ou aguarde.")
        if r.status_code == 404:
            raise ExternalServiceError("Repositório não encontrado ou sem permissão de acesso (404).")
        if r.status_code >= 400:
            raise ExternalServiceError(f"Erro da API GitHub ({r.status_code}).")
        data = r.json()
        _cache[key] = (time.monotonic(), data)
        return data

    def get_fresh(self, db: Session, path: str, params: dict[str, Any] | None = None) -> Any:
        """Como ``_get`` mas sem cache (para gatilhos que procuram eventos novos)."""
        key = path + repr(sorted((params or {}).items()))
        _cache.pop(key, None)
        return self._get(db, path, params)

    def repo_activity(self, db: Session, url: str) -> dict[str, Any]:
        """Branches, commits recentes, pull requests, issues e releases de um repositório."""
        owner, repo = parse_repo(url)
        base = f"/repos/{owner}/{repo}"
        commits = self._get(db, f"{base}/commits", {"per_page": 30})
        branches = self._get(db, f"{base}/branches", {"per_page": 30})
        pulls = self._get(db, f"{base}/pulls", {"state": "all", "per_page": 30, "sort": "updated", "direction": "desc"})
        issues = self._get(db, f"{base}/issues", {"state": "all", "per_page": 30})
        releases = self._get(db, f"{base}/releases", {"per_page": 10})
        return {
            "repo": f"{owner}/{repo}",
            "url": f"https://github.com/{owner}/{repo}",
            "commits": [
                {
                    "sha": c.get("sha", "")[:7],
                    "message": (c.get("commit", {}).get("message") or "").split("\n")[0][:300],
                    "author": (c.get("commit", {}).get("author") or {}).get("name") or "",
                    "date": (c.get("commit", {}).get("author") or {}).get("date"),
                    "url": c.get("html_url") or "",
                }
                for c in commits
            ],
            "branches": [{"name": b.get("name"), "sha": (b.get("commit") or {}).get("sha", "")[:7]} for b in branches],
            "pulls": [
                {
                    "number": p.get("number"),
                    "title": p.get("title") or "",
                    "body": (p.get("body") or "")[:2000],
                    "state": "merged" if p.get("merged_at") else p.get("state"),
                    "branch": (p.get("head") or {}).get("ref") or "",
                    "author": (p.get("user") or {}).get("login") or "",
                    "url": p.get("html_url") or "",
                    "date": p.get("updated_at"),
                }
                for p in pulls
            ],
            "issues": [
                {
                    "number": i.get("number"),
                    "title": i.get("title") or "",
                    "body": (i.get("body") or "")[:2000],
                    "state": i.get("state"),
                    "author": (i.get("user") or {}).get("login") or "",
                    "url": i.get("html_url") or "",
                    "date": i.get("updated_at"),
                }
                for i in issues
                if "pull_request" not in i
            ],
            "releases": [
                {
                    "tag": r.get("tag_name"),
                    "name": r.get("name") or "",
                    "date": r.get("published_at"),
                    "url": r.get("html_url"),
                }
                for r in releases
            ],
        }

    def status(self, db: Session) -> dict[str, Any]:
        i = self._integration(db)
        return {
            "provider": self.provider,
            "label": self.label,
            "status": i.status,
            "config": i.config,
            "has_token": bool(i.secret_id),
            "secret_id": i.secret_id,
            "last_checked_at": i.last_checked_at,
            "last_error": i.last_error,
            "capabilities": ["repo_metadata", "commits", "branches", "pull_requests", "issues", "releases", "events"],
            "help": "Crie um fine-grained token em GitHub → Settings → Developer settings, com acesso "
            "de leitura a 'Contents', 'Metadata', 'Issues' e 'Pull requests'. Guarde-o no Cofre e "
            "associe-o aqui.",
        }

    def configure(self, db: Session, secret_id: str | None) -> dict[str, Any]:
        i = self._integration(db)
        if secret_id:
            get_or_404(db, SecretEntry, secret_id)
        i.secret_id = secret_id
        i.status = "not_configured"
        i.config = {}
        _cache.clear()
        log_activity(
            db,
            "integration",
            i.id,
            "configured",
            "Integração GitHub configurada" if secret_id else "Token GitHub removido da integração",
        )
        if secret_id:
            return self.test(db)
        return self.status(db)

    def test(self, db: Session) -> dict[str, Any]:
        i = self._integration(db)
        i.last_checked_at = utcnow()
        if not i.secret_id:
            i.status, i.last_error = "not_configured", ""
            return self.status(db)
        _cache.clear()
        try:
            user = self._get(db, "/user")
            i.status, i.last_error = "connected", ""
            i.config = {"login": user.get("login"), "name": user.get("name")}
        except ExternalServiceError as e:
            i.status, i.last_error = "error", e.message
        return self.status(db)

    def repo_overview(self, db: Session, url: str) -> dict[str, Any]:
        owner, repo = parse_repo(url)
        meta = self._get(db, f"/repos/{owner}/{repo}")
        commits = self._get(db, f"/repos/{owner}/{repo}/commits", {"per_page": 5})
        pulls = self._get(db, f"/repos/{owner}/{repo}/pulls", {"state": "open", "per_page": 5})
        return {
            "source": "api.github.com",
            "fetched_at": utcnow(),
            "repo": {
                "full_name": meta.get("full_name"),
                "description": meta.get("description"),
                "html_url": meta.get("html_url"),
                "private": meta.get("private"),
                "default_branch": meta.get("default_branch"),
                "stars": meta.get("stargazers_count"),
                "open_issues": meta.get("open_issues_count"),
                "pushed_at": meta.get("pushed_at"),
                "language": meta.get("language"),
            },
            "commits": [
                {
                    "sha": c.get("sha", "")[:7],
                    "message": (c.get("commit", {}).get("message") or "").split("\n")[0][:200],
                    "author": (c.get("commit", {}).get("author") or {}).get("name"),
                    "date": (c.get("commit", {}).get("author") or {}).get("date"),
                    "url": c.get("html_url"),
                }
                for c in commits
            ],
            "pull_requests": [
                {
                    "number": p.get("number"),
                    "title": p.get("title"),
                    "url": p.get("html_url"),
                    "author": (p.get("user") or {}).get("login"),
                }
                for p in pulls
            ],
        }
