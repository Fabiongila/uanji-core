"""Fundações: autenticação, migrações, erros, segurança HTTP."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from uanji.db import head_revision


def test_health_is_public(anon: TestClient) -> None:
    assert anon.get("/health").json()["status"] == "ok"


def test_api_requires_token(anon: TestClient) -> None:
    r = anon.get("/api/projects")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    r = anon.get("/api/projects", headers={"Authorization": "Bearer errado"})
    assert r.status_code == 401


def test_rejects_foreign_host(client: TestClient) -> None:
    r = client.get("/api/projects", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_fresh_database_is_migrated_to_head(client: TestClient, data_dir) -> None:  # type: ignore[no-untyped-def]
    conn = sqlite3.connect(data_dir / "uanji.db")
    rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert rev == head_revision(f"sqlite:///{data_dir / 'uanji.db'}")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"projects", "tasks", "notes", "search_index", "automations", "secrets"} <= tables
    conn.close()


def test_builtin_templates_seeded_once(client: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    templates = client.get("/api/checklists", params={"is_template": True}).json()
    assert len(templates) == 7
    from uanji.services.checklists import seed_builtin_templates

    with app.state.database.session() as db:
        assert seed_builtin_templates(db) == 0


def test_validation_error_format(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": ""})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["details"]["errors"][0]["field"] == "name"


def test_not_found_format(client: TestClient) -> None:
    r = client.get("/api/projects/nao-existe")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_openapi_available(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert "/api/projects" in spec["paths"]


def test_client_errors_are_logged(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/diagnostics/client-error", json={"message": "x", "source": "react:/", "stack": "s"})
    assert r.json() == {"ok": True}
    assert any("Erro na interface" in line for line in client.get("/api/diagnostics/logs").json()["lines"])
