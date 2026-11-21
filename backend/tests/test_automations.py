"""Motor de automações: validação, execução, gatilhos, idempotência, falhas e versões."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from uanji.automation import engine


def _defn(steps, trigger=None, conditions=None):  # type: ignore[no-untyped-def]
    return {"trigger": trigger or {"type": "manual"}, "conditions": conditions or [], "steps": steps}


def _create(client: TestClient, definition, enabled=True, name="Auto"):  # type: ignore[no-untyped-def]
    r = client.post("/api/automations", json={"name": name, "definition": definition, "enabled": enabled})
    assert r.status_code == 201, r.text
    return r.json()


def test_validation_rejects_unknown_action_and_bad_params(client: TestClient) -> None:
    r = client.post("/api/automations/validate", json=_defn([{"id": "s1", "action": "shell", "params": {}}]))
    assert r.json()["valid"] is False
    r = client.post("/api/automations/validate", json=_defn([{"id": "s1", "action": "create_task", "params": {}}]))
    errs = r.json()["errors"]
    assert errs and errs[0]["step"] == "s1"
    r = client.post(
        "/api/automations/validate",
        json=_defn(
            [{"id": "s1", "action": "notify", "params": {"title": "x"}}],
            trigger={"type": "schedule", "config": {"mode": "interval", "minutes": 1}},
        ),
    )
    assert r.json()["valid"] is False  # intervalo mínimo
    assert client.post("/api/automations", json={"name": "x", "definition": _defn([])}).status_code == 422


def test_manual_run_sequential_with_templating(client: TestClient) -> None:
    a = _create(
        client,
        _defn(
            [
                {"id": "t", "action": "create_task", "params": {"title": "Gerada", "priority": "high"}},
                {
                    "id": "n",
                    "action": "create_note",
                    "params": {"title": "Sobre {{steps.t.title}}", "content": "id={{steps.t.task_id}}"},
                },
                {"id": "l", "action": "log_event", "params": {"message": "ok {{automation.name}}"}},
            ]
        ),
    )
    run = client.post(f"/api/automations/{a['id']}/run").json()
    assert run["status"] == "success", run
    assert [s["status"] for s in run["steps"]] == ["success"] * 3
    assert run["duration_ms"] is not None
    task_id = run["steps"][0]["output"]["task_id"]
    note = client.get(f"/api/notes/{run['steps'][1]['output']['note_id']}").json()
    assert note["title"] == "Sobre Gerada" and note["content"] == f"id={task_id}"
    assert client.get(f"/api/automations/{a['id']}/runs").json()[0]["status"] == "success"


def test_failure_stops_and_notifies_without_rollback(client: TestClient) -> None:
    a = _create(
        client,
        _defn(
            [
                {"id": "ok", "action": "create_task", "params": {"title": "Antes da falha"}},
                {"id": "bad", "action": "update_task_status", "params": {"task_id": "inexistente", "status": "done"}},
                {"id": "never", "action": "create_task", "params": {"title": "Nunca"}},
            ]
        ),
        name="Falha",
    )
    run = client.post(f"/api/automations/{a['id']}/run").json()
    assert run["status"] == "failed" and "bad" in run["error"]
    assert len(run["steps"]) == 2
    titles = [t["title"] for t in client.get("/api/tasks").json()["items"]]
    assert "Antes da falha" in titles and "Nunca" not in titles  # sem rollback, documentado
    notes = client.get("/api/notifications").json()
    assert any(n["category"] == "automation" and n["level"] == "error" for n in notes)


def test_conditions_skip(client: TestClient) -> None:
    a = _create(
        client,
        _defn(
            [{"id": "s", "action": "log_event", "params": {"message": "x"}}],
            conditions=[{"field": "trigger.source", "op": "eq", "value": "outro"}],
        ),
    )
    run = client.post(f"/api/automations/{a['id']}/run").json()
    assert run["status"] == "cancelled" and "Condição" in run["error"]


def test_task_completed_trigger_is_idempotent(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "P"}).json()
    a = _create(
        client,
        _defn(
            [{"id": "n", "action": "notify", "params": {"title": "Concluída: {{trigger.title}}"}}],
            trigger={"type": "task_completed", "config": {"project_id": p["id"]}},
        ),
    )
    other = client.post("/api/tasks", json={"title": "Fora"}).json()
    client.post(f"/api/tasks/{other['id']}/status", json={"status": "done"})
    t = client.post("/api/tasks", json={"title": "Dentro", "project_id": p["id"]}).json()
    client.post(f"/api/tasks/{t['id']}/status", json={"status": "done"})
    runs = client.get(f"/api/automations/{a['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["trigger"] == "task_completed"
    detail = client.get(f"/api/automation-runs/{runs[0]['id']}").json()
    assert detail["steps"][0]["input"]["title"] == "Concluída: Dentro"
    # Mesmo evento repetido → sem execução duplicada.
    done = client.get(f"/api/tasks/{t['id']}").json()
    payload = {"task_id": t["id"], "title": "Dentro", "project_id": p["id"], "completed_at": done["completed_at"]}
    engine.on_task_completed("task.completed", payload)
    assert len(client.get(f"/api/automations/{a['id']}/runs").json()) == 1


def test_chained_automations_depth_limited(client: TestClient) -> None:
    # Automação que reabre e conclui... não pode criar ciclos infinitos.
    _create(
        client,
        _defn(
            [{"id": "c", "action": "create_task", "params": {"title": "Eco {{trigger.title}}"}}],
            trigger={"type": "task_completed", "config": {}},
        ),
    )
    t = client.post("/api/tasks", json={"title": "Origem"}).json()
    client.post(f"/api/tasks/{t['id']}/status", json={"status": "done"})
    titles = [x["title"] for x in client.get("/api/tasks").json()["items"]]
    assert titles.count("Eco Origem") == 1


def test_schedule_and_deadline_triggers(client: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    a = _create(
        client,
        _defn(
            [{"id": "s", "action": "generate_summary", "params": {"scope": "today"}}],
            trigger={"type": "schedule", "config": {"mode": "interval", "minutes": 60}},
        ),
    )
    assert a["next_run_at"] is not None
    from uanji.models import Automation

    with app.state.database.session() as db:
        db.get(Automation, a["id"]).next_run_at = datetime.now(UTC) - timedelta(minutes=1)
    runs = engine.scheduler_tick()
    assert len(runs) == 1
    assert engine.scheduler_tick() == []  # próxima execução já reagendada
    run = client.get(f"/api/automation-runs/{runs[0]}").json()
    assert run["status"] == "success" and "Resumo" in run["steps"][0]["output"]["summary"]

    d = _create(
        client,
        _defn(
            [{"id": "n", "action": "notify", "params": {"title": "Prazo {{trigger.title}}"}}],
            trigger={"type": "deadline_approaching", "config": {"hours": 24}},
        ),
        name="Prazo",
    )
    client.post("/api/tasks", json={"title": "Urgente", "due_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat()})
    engine.scheduler_tick()
    engine.scheduler_tick()
    assert len(client.get(f"/api/automations/{d['id']}/runs").json()) == 1


def test_versions_and_rollback(client: TestClient) -> None:
    a = _create(client, _defn([{"id": "s", "action": "log_event", "params": {"message": "v1"}}]))
    upd = client.patch(
        f"/api/automations/{a['id']}",
        json={"definition": _defn([{"id": "s", "action": "log_event", "params": {"message": "v2"}}])},
    ).json()
    assert upd["version"] == 2
    same = client.patch(f"/api/automations/{a['id']}", json={"definition": upd["definition"]}).json()
    assert same["version"] == 2  # sem alterações → sem nova versão
    rb = client.post(f"/api/automations/{a['id']}/rollback", json={"version": 1}).json()
    assert rb["version"] == 3 and rb["definition"]["steps"][0]["params"]["message"] == "v1"
    assert len(client.get(f"/api/automations/{a['id']}/versions").json()) == 3


def test_disabled_automation_not_triggered_and_delete_confirm(client: TestClient) -> None:
    a = _create(
        client,
        _defn(
            [{"id": "s", "action": "log_event", "params": {"message": "x"}}],
            trigger={"type": "task_completed", "config": {}},
        ),
        enabled=False,
    )
    t = client.post("/api/tasks", json={"title": "T"}).json()
    client.post(f"/api/tasks/{t['id']}/status", json={"status": "done"})
    assert client.get(f"/api/automations/{a['id']}/runs").json() == []
    assert client.delete(f"/api/automations/{a['id']}").status_code == 428
    assert client.delete(f"/api/automations/{a['id']}", params={"confirm": True}).status_code == 204


def test_cancel_finished_run_conflict(client: TestClient) -> None:
    a = _create(client, _defn([{"id": "s", "action": "log_event", "params": {"message": "x"}}]))
    run = client.post(f"/api/automations/{a['id']}/run").json()
    assert client.post(f"/api/automation-runs/{run['id']}/cancel").status_code == 409


def test_render_never_evaluates() -> None:
    ctx = {"a": {"b": "ok"}}
    assert engine.render("{{a.b}}", ctx) == "ok"
    assert engine.render("{{__import__('os')}}", ctx) == "{{__import__('os')}}"
    assert engine.render("x {{a.missing}} y", ctx) == "x  y"
