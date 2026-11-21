"""Projectos, tarefas, dependências, foco e regras de progresso."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _project(client: TestClient, **kw) -> dict:  # type: ignore[no-untyped-def]
    r = client.post("/api/projects", json={"name": "UANJI", "status": "active", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _task(client: TestClient, **kw) -> dict:  # type: ignore[no-untyped-def]
    r = client.post("/api/tasks", json={"title": "Tarefa", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_project_crud_and_history(client: TestClient) -> None:
    p = _project(client, description="Centro de comando")
    assert p["progress"]["percent"] is None  # sem tarefas: sem critério
    r = client.patch(f"/api/projects/{p['id']}", json={"status": "paused"})
    assert r.json()["status"] == "paused"
    hist = client.get(f"/api/projects/{p['id']}/history").json()
    assert any("paused" in h["summary"] for h in hist)
    r = client.post(f"/api/projects/{p['id']}/archive", json={"archived": True})
    assert r.json()["archived_at"] is not None
    assert client.get("/api/projects").json()["total"] == 0
    assert client.get("/api/projects", params={"include_archived": True}).json()["total"] == 1


def test_project_blocked_requires_reason(client: TestClient) -> None:
    p = _project(client)
    r = client.patch(f"/api/projects/{p['id']}", json={"status": "blocked"})
    assert r.status_code == 422
    r = client.patch(f"/api/projects/{p['id']}", json={"status": "blocked", "blocked_reason": "API externa"})
    assert r.status_code == 200


def test_project_dates_validated(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "X", "start_date": "2026-05-10", "due_date": "2026-05-01"})
    assert r.status_code == 422


def test_delete_requires_confirmation_and_detaches_tasks(client: TestClient) -> None:
    p = _project(client)
    t = _task(client, project_id=p["id"])
    r = client.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 428
    assert r.json()["error"]["details"]["tasks_detached"] == 1
    assert client.delete(f"/api/projects/{p['id']}", params={"confirm": True}).status_code == 204
    assert client.get(f"/api/tasks/{t['id']}").json()["project_id"] is None


def test_progress_rule(client: TestClient) -> None:
    p = _project(client)
    a = _task(client, project_id=p["id"])
    _task(client, project_id=p["id"])
    _task(client, project_id=p["id"], parent_id=a["id"])  # subtarefa não conta
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "done"})  # bloqueado por subtarefa
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert detail["progress"]["tasks_total"] == 2
    assert detail["progress"]["percent"] == 0


def test_task_lifecycle(client: TestClient) -> None:
    t = _task(client, priority="high")
    r = client.post(f"/api/tasks/{t['id']}/status", json={"status": "done"})
    assert r.json()["completed_at"] is not None
    r = client.post(f"/api/tasks/{t['id']}/status", json={"status": "todo"})
    assert r.json()["completed_at"] is None
    r = client.post(f"/api/tasks/{t['id']}/archive", json={"archived": True})
    assert r.json()["archived_at"]
    assert client.get("/api/tasks").json()["total"] == 0
    assert client.get("/api/tasks", params={"include_archived": True}).json()["total"] == 1


def test_subtasks_block_parent_completion(client: TestClient) -> None:
    parent = _task(client)
    sub = _task(client, parent_id=parent["id"])
    r = client.post(f"/api/tasks/{parent['id']}/status", json={"status": "done"})
    assert r.status_code == 422
    client.post(f"/api/tasks/{sub['id']}/status", json={"status": "done"})
    r = client.post(f"/api/tasks/{parent['id']}/status", json={"status": "done"})
    assert r.status_code == 200
    assert client.get(f"/api/tasks/{parent['id']}").json()["subtasks_done"] == 1


def test_dependencies_and_cycles(client: TestClient) -> None:
    a, b = _task(client, title="A"), _task(client, title="B")
    r = client.post(f"/api/tasks/{b['id']}/dependencies", json={"depends_on_id": a["id"]})
    assert r.json()["blocked_by_open"] == 1
    r = client.post(f"/api/tasks/{a['id']}/dependencies", json={"depends_on_id": b["id"]})
    assert r.status_code == 422 and "ciclo" in r.json()["error"]["message"]
    assert client.post(f"/api/tasks/{b['id']}/status", json={"status": "done"}).status_code == 422
    client.post(f"/api/tasks/{a['id']}/status", json={"status": "done"})
    assert client.post(f"/api/tasks/{b['id']}/status", json={"status": "done"}).status_code == 200


def test_overdue_and_filters(client: TestClient) -> None:
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    _task(client, title="Atrasada", due_at=past)
    _task(client, title="Sem prazo")
    overdue = client.get("/api/tasks", params={"due": "overdue"}).json()
    assert [t["title"] for t in overdue["items"]] == ["Atrasada"]
    assert overdue["items"][0]["overdue"] is True
    assert client.get("/api/tasks", params={"q": "prazo"}).json()["total"] == 1


def test_naive_datetime_rejected(client: TestClient) -> None:
    r = client.post("/api/tasks", json={"title": "X", "due_at": "2026-01-01T10:00:00"})
    assert r.status_code == 422


def test_postpone_counted(client: TestClient) -> None:
    d1 = datetime.now(UTC) + timedelta(days=1)
    t = _task(client, due_at=d1.isoformat())
    r = client.patch(f"/api/tasks/{t['id']}", json={"due_at": (d1 + timedelta(days=2)).isoformat()})
    assert r.json()["postponed_count"] == 1


def test_focus_sessions(client: TestClient) -> None:
    t = _task(client)
    assert client.post("/api/focus/start", json={"task_id": t["id"]}).status_code == 201
    assert client.post("/api/focus/start", json={}).status_code == 409
    s = client.post("/api/focus/stop").json()
    assert s["ended_at"] is not None
    r = client.post(
        "/api/focus/log", json={"task_id": t["id"], "started_at": datetime.now(UTC).isoformat(), "minutes": 25}
    )
    assert r.json()["duration_seconds"] == 1500
    d = client.get("/api/dashboard").json()
    assert d["counters"]["focus_minutes_today"] >= 25


def test_links_and_milestones(client: TestClient) -> None:
    p = _project(client)
    link = client.post(f"/api/projects/{p['id']}/links", json={"url": "https://github.com/foo/bar"}).json()
    assert link["kind"] == "github"
    assert client.post(f"/api/projects/{p['id']}/links", json={"url": "javascript:alert(1)"}).status_code == 422
    m = client.post(f"/api/projects/{p['id']}/milestones", json={"title": "MVP"}).json()
    client.put(f"/api/milestones/{m['id']}", json={"title": "MVP", "done": True})
    detail = client.get(f"/api/projects/{p['id']}").json()
    assert detail["progress"]["milestones_done"] == 1
