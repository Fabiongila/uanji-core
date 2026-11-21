"""Automação visual (condições, resultados, gatilhos externos), centro de desempenho,
integração com desenvolvimento, Command Palette e modelo de IA próprio."""

# ruff: noqa: F811, S603, S607  (fixture «voice» importada; git chamado com argumentos fixos)
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from uanji.automation import engine
from uanji.integrations import github
from uanji.models import Automation, FocusSession, Task
from uanji.system import macos

from .test_assistant_voice import say, voice  # noqa: F401


def task(client: TestClient, title: str, **extra: Any) -> dict[str, Any]:
    r = client.post("/api/tasks", json={"title": title, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def project(client: TestClient, name: str) -> dict[str, Any]:
    r = client.post("/api/projects", json={"name": name, "status": "active"})
    assert r.status_code == 201, r.text
    return r.json()


def automation(client: TestClient, definition: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
    r = client.post("/api/automations", json={"name": "Fluxo", "enabled": enabled, "definition": definition})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- 03 · Desempenho


def test_task_numbers_cycle_and_blocked_time(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    a = task(client, "Primeira")
    b = task(client, "Segunda")
    assert (a["number"], b["number"]) == (1, 2)
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "in_progress"})
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "blocked", "blocked_reason": "À espera da API"})
    with app.state.database.session() as db:
        t = db.get(Task, a["id"])
        assert t is not None and t.started_at is not None and t.blocked_at is not None
        # Simula: começou há 3 dias e esteve bloqueada 2 horas.
        t.started_at = datetime.now(UTC) - timedelta(days=3)
        t.blocked_at = datetime.now(UTC) - timedelta(hours=2)
        db.add(
            FocusSession(
                started_at=datetime.now(UTC) - timedelta(hours=1), ended_at=datetime.now(UTC), duration_seconds=600
            )
        )
    perf = client.get("/api/performance").json()
    assert perf["blocked"]["now"] == 1 and perf["blocked"]["items"][0]["hours"] >= 1.9
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "in_progress"})
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "done"})
    perf = client.get("/api/performance").json()
    assert perf["cycle_time"]["count"] == 1 and 71 <= perf["cycle_time"]["avg_h"] <= 73
    assert perf["blocked"]["now"] == 0 and perf["blocked"]["total_hours_in_done"] >= 1.9
    assert perf["interruptions"]["short_focus"] == 1
    assert perf["interruptions"]["regressions"] >= 1  # em curso → bloqueada
    assert len(perf["weekly"]) == 8 and perf["weekly"][-1]["done"] == 1


def test_performance_project_filter_scopes_interruptions(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    a, b = project(client, "A"), project(client, "B")
    ta = task(client, "Da A", project_id=a["id"])
    client.post(f"/api/tasks/{ta['id']}/status", json={"status": "in_progress"})
    client.post(f"/api/tasks/{ta['id']}/status", json={"status": "todo"})
    now = datetime.now(UTC)
    with app.state.database.session() as db:
        db.add(
            FocusSession(project_id=a["id"], started_at=now - timedelta(hours=1), ended_at=now, duration_seconds=300)
        )
    ia = client.get("/api/performance", params={"project_id": a["id"]}).json()["interruptions"]
    ib = client.get("/api/performance", params={"project_id": b["id"]}).json()["interruptions"]
    assert (ia["short_focus"], ia["regressions"]) == (1, 1)
    assert (ib["short_focus"], ib["regressions"]) == (0, 0)
    assert ib["app_switches_scope"] == "project_filter"


def test_goals_and_versions_progress(client: TestClient) -> None:
    p = project(client, "Q360")
    g = client.post("/api/goals", json={"title": "API pública v1", "project_id": p["id"]}).json()
    v = client.post(f"/api/projects/{p['id']}/versions", json={"name": "v0.4", "git_tag": "v0.4.0"}).json()
    assert client.post(f"/api/projects/{p['id']}/versions", json={"name": "v0.4"}).status_code == 422
    t1 = task(client, "Paginação", project_id=p["id"], goal_id=g["id"], version_id=v["id"])
    task(client, "Autenticação", project_id=p["id"], goal_id=g["id"], version_id=v["id"])
    client.post(f"/api/tasks/{t1['id']}/status", json={"status": "done"})
    goals = client.get("/api/goals").json()
    assert goals[0]["percent"] == 50 and goals[0]["project_name"] == "Q360"
    assert client.get(f"/api/projects/{p['id']}/versions").json()[0]["percent"] == 50
    released = client.put(
        f"/api/projects/{p['id']}/versions/{v['id']}", json={"name": "v0.4", "status": "released", "git_tag": "v0.4.0"}
    ).json()
    assert released["released_at"]
    assert client.get("/api/performance").json()["goals"][0]["tasks_done"] == 1
    assert client.post("/api/tasks", json={"title": "x", "goal_id": "nao-existe"}).status_code == 404


# --------------------------------------------------------------------------- 04 · Código


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "Fabio",
            "GIT_AUTHOR_EMAIL": "f@x",
            "GIT_COMMITTER_NAME": "Fabio",
            "GIT_COMMITTER_EMAIL": "f@x",
            "HOME": str(repo),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


@pytest.fixture
def local_repo(tmp_path: Path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    repo = tmp_path / "q360-backend"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "src").mkdir()
    (repo / "src" / "pagination.py").write_text("x = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "feat: paginação por cursor UJ-1")
    git(repo, "checkout", "-q", "-b", "feature/uj-2-auth")
    git(repo, "commit", "-q", "--allow-empty", "-m", "wip auth")
    return repo


def test_local_repo_links_commits_and_branches_to_tasks(client: TestClient, local_repo: Path) -> None:
    p = project(client, "Q360")
    t1 = task(client, "Paginação", project_id=p["id"])
    t2 = task(client, "Autenticação", project_id=p["id"])
    assert client.post(f"/api/projects/{p['id']}/code/sync").status_code == 422  # sem repositórios
    lk = client.post(
        f"/api/projects/{p['id']}/links", json={"kind": "folder", "url": str(local_repo), "title": "backend"}
    )
    assert lk.status_code == 201, lk.text
    r = client.post(f"/api/projects/{p['id']}/code/sync").json()
    assert r["new_links"] == 2 and not r["errors"]
    code1 = client.get(f"/api/tasks/{t1['id']}/code").json()
    assert code1["ref"] == "UJ-1" and code1["links"][0]["kind"] == "commit"
    code2 = client.get(f"/api/tasks/{t2['id']}/code").json()
    assert code2["links"][0] == {**code2["links"][0], "kind": "branch", "ref": "feature/uj-2-auth"}
    again = client.post(f"/api/projects/{p['id']}/code/sync").json()
    assert again["new_links"] == 0  # idempotente
    view = client.get(f"/api/projects/{p['id']}/code").json()["repos"][0]
    assert view["commits"][-1]["tasks"][0]["ref"] == "UJ-1"


def test_github_activity_links_prs_and_issues(client: TestClient) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        data: Any = []
        if path.endswith("/commits"):
            data = [
                {
                    "sha": "a3f9c21aaaa",
                    "commit": {"message": "fix login UJ-1", "author": {"name": "F", "date": "2026-10-30T10:00:00Z"}},
                    "html_url": "u",
                }
            ]
        elif path.endswith("/branches"):
            data = [{"name": "main", "commit": {"sha": "a3f9c21"}}]
        elif path.endswith("/pulls"):
            data = [
                {
                    "number": 12,
                    "title": "Auth JWT",
                    "body": "Fecha UJ-1",
                    "merged_at": "2026-10-30T11:00:00Z",
                    "state": "closed",
                    "head": {"ref": "auth"},
                    "user": {"login": "f"},
                    "html_url": "pr12",
                    "updated_at": "2026-10-30T11:00:00Z",
                }
            ]
        elif path.endswith("/issues"):
            data = [
                {"number": 19, "title": "Erro 500 UJ-1", "state": "open", "user": {"login": "f"}, "html_url": "i19"},
                {"number": 12, "title": "PR", "pull_request": {}},
            ]
        return httpx.Response(200, json=data)

    github.transport = httpx.MockTransport(handler)
    github._cache.clear()
    try:
        p = project(client, "Q360")
        t1 = task(client, "Login", project_id=p["id"])
        client.post(f"/api/projects/{p['id']}/links", json={"kind": "github", "url": "https://github.com/foo/q360"})
        assert client.post(f"/api/projects/{p['id']}/code/sync").json()["new_links"] == 3
        kinds = {link["kind"]: link for link in client.get(f"/api/tasks/{t1['id']}/code").json()["links"]}
        assert set(kinds) == {"commit", "pr", "issue"} and kinds["pr"]["state"] == "merged"
    finally:
        github.transport = None
        github._cache.clear()


# --------------------------------------------------------------------------- 02 · Automação visual


def test_condition_nodes_skip_or_stop(app, client: TestClient) -> None:
    a = automation(
        client,
        {
            "trigger": {"type": "manual", "config": {}},
            "steps": [
                {"id": "s1", "action": "create_task", "params": {"title": "Sempre"}},
                {
                    "id": "s2",
                    "action": "create_task",
                    "params": {"title": "Nunca"},
                    "conditions": [{"field": "trigger.source", "op": "eq", "value": "outra"}],
                    "on_false": "skip",
                },
                {"id": "s3", "action": "notify", "params": {"title": "Resultado"}},
                {
                    "id": "s4",
                    "action": "create_task",
                    "params": {"title": "Depois da paragem"},
                    "conditions": [{"field": "steps.s1.task_id", "op": "not_exists"}],
                    "on_false": "stop",
                },
                {"id": "s5", "action": "create_task", "params": {"title": "Não deve correr"}},
            ],
        },
    )
    run = client.post(f"/api/automations/{a['id']}/run").json()
    statuses = [s["status"] for s in run["steps"]]
    assert statuses == ["success", "skipped", "success", "skipped"] and run["status"] == "cancelled"
    titles = {t["title"] for t in client.get("/api/tasks").json()["items"]}
    assert titles == {"Sempre"}
    catalog = {c["name"]: c for c in client.get("/api/automations/actions").json()}
    assert catalog["notify"]["category"] == "result" and catalog["speak"]["category"] == "result"
    assert catalog["create_task"]["category"] == "action" and "call_webhook" in catalog


def test_webhook_trigger_from_external_app(client: TestClient) -> None:
    a = automation(
        client,
        {
            "trigger": {"type": "webhook", "config": {}},
            "steps": [{"id": "s1", "action": "create_task", "params": {"title": "{{trigger.title}}"}}],
        },
    )
    info = client.post(f"/api/automations/{a['id']}/webhook").json()
    assert info["url"].endswith(f"/hooks/{a['id']}") and info["secret"]
    hook = f"/hooks/{a['id']}"
    anon = TestClient(client.app)
    assert anon.post(hook, json={"title": "x"}).status_code == 422
    assert anon.post(hook, json={"title": "x"}, headers={"X-UANJI-Secret": "errado"}).status_code == 422
    r = anon.post(hook, json={"title": "Pedido do formulário"}, headers={"X-UANJI-Secret": info["secret"]})
    assert r.status_code == 200 and r.json()["run_id"]
    assert client.get("/api/tasks").json()["items"][0]["title"] == "Pedido do formulário"
    dup = anon.post(hook, json={"title": "y"}, headers={"X-UANJI-Secret": info["secret"], "X-Idempotency-Key": "k1"})
    dup2 = anon.post(hook, json={"title": "y"}, headers={"X-UANJI-Secret": info["secret"], "X-Idempotency-Key": "k1"})
    assert dup.json()["run_id"] and dup2.json()["run_id"] is None


def test_app_opened_and_github_triggers(app, client: TestClient) -> None:
    a = automation(
        client,
        {
            "trigger": {"type": "app_opened", "config": {"app": "Xcode"}},
            "steps": [{"id": "s1", "action": "log_event", "params": {"message": "Abriu {{trigger.app}}"}}],
        },
    )
    assert engine.on_app_activated("Safari") == []
    assert len(engine.on_app_activated("Xcode")) == 1
    assert engine.on_app_activated("Xcode") == []  # no máximo uma vez a cada 30 min

    commits = [{"sha": "aaa1111", "commit": {"message": "primeiro", "author": {"name": "F"}}, "html_url": "u1"}]
    github.transport = httpx.MockTransport(lambda req: httpx.Response(200, json=commits))
    github._cache.clear()
    try:
        g = automation(
            client,
            {
                "trigger": {"type": "github", "config": {"repo_url": "https://github.com/foo/bar", "event": "push"}},
                "steps": [{"id": "s1", "action": "create_task", "params": {"title": "Rever {{trigger.sha}}"}}],
            },
        )
        assert engine.poll_github() == []  # primeira verificação só regista a referência
        commits.insert(0, {"sha": "bbb2222", "commit": {"message": "novo", "author": {"name": "F"}}, "html_url": "u2"})
        with app.state.database.session() as db:
            row = db.get(Automation, g["id"])
            assert row is not None
            row.trigger_state = {**row.trigger_state, "checked_at": "2000-01-01T00:00:00+00:00"}
        assert len(engine.poll_github()) == 1
        assert any(t["title"] == "Rever bbb2222" for t in client.get("/api/tasks").json()["items"])
    finally:
        github.transport = None
        github._cache.clear()
    bad = client.post(
        "/api/automations",
        json={
            "name": "x",
            "definition": {
                "trigger": {"type": "github", "config": {"repo_url": "https://gitlab.com/a/b"}},
                "steps": [{"id": "s1", "action": "notify", "params": {"title": "x"}}],
            },
        },
    )
    assert bad.status_code == 422
    assert a["id"]


# --------------------------------------------------------------------------- 05 · Command Palette


def test_palette_finds_and_opens_project_files(client: TestClient, local_repo: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []
    monkeypatch.setattr(macos, "runner", lambda args, **kw: calls.append(args) or macos.RunResult(0, "", ""))
    assert client.get("/api/palette/files", params={"q": "pagin"}).json()["files"] == []
    p = project(client, "Q360")
    client.post(f"/api/projects/{p['id']}/links", json={"kind": "folder", "url": str(local_repo)})
    files = client.get("/api/palette/files", params={"q": "pagin"}).json()["files"]
    assert files[0]["relative"] == "src/pagination.py"
    assert client.post("/api/palette/open-file", json={"path": files[0]["path"]}).status_code == 200
    assert calls[-1][-1] == files[0]["path"]
    outside = client.post("/api/palette/open-file", json={"path": "/etc/hosts"})
    assert outside.status_code == 422


# --------------------------------------------------------------------------- Modelo de IA próprio


def test_own_model_openai_compatible(client: TestClient, voice, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from uanji.assistant import openai_compat

    seen: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "qwen2.5:7b"}]})
        body = json.loads(req.content)
        if "tools" not in body:
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        seen.append(body)
        if len(seen) == 1:
            assert body["tools"] and body["messages"][0]["role"] == "system"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {"name": "list_projects", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        assert body["messages"][-1]["role"] == "tool"
        return httpx.Response(200, json={"choices": [{"message": {"content": "Não tem projectos registados."}}]})

    real = openai_compat.OpenAICompatibleProvider.__init__

    def init(self, base_url, model, api_key=None, timeout=180.0, transport=None):  # type: ignore[no-untyped-def]
        real(self, base_url, model, api_key, timeout, httpx.MockTransport(handler))

    monkeypatch.setattr(openai_compat.OpenAICompatibleProvider, "__init__", init)
    bad = client.patch(
        "/api/settings",
        json={
            "values": {
                "assistant": {"provider": "openai_compatible", "base_url": "http://192.168.1.5:11434/v1", "model": "x"}
            }
        },
    )
    assert bad.status_code == 422  # http só para localhost
    ok = client.patch(
        "/api/settings",
        json={
            "values": {
                "assistant": {
                    "provider": "openai_compatible",
                    "base_url": "http://localhost:11434/v1/",
                    "model": "qwen2.5:7b",
                }
            }
        },
    )
    assert ok.json()["assistant"]["base_url"] == "http://localhost:11434/v1"
    st = client.get("/api/assistant/status").json()
    assert st["configured"] and st["local"] and st["provider"] == "openai_compatible"
    out = say(client, "qual é a capital de França?")
    assert out["engine"] == "ai" and out["reply"] == "Não tem projectos registados."
    assert out["consulted"][0]["tool"] == "list_projects"
    seen.clear()
    test = client.post("/api/assistant/test").json()
    assert test["ok"] and test["model_found"] is True
