"""Notas, revisões, conhecimento, checklists/modelos, pesquisa e comandos."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_note_autosave_revisions_and_conflict(client: TestClient) -> None:
    n = client.post("/api/notes", json={"title": "Arquitectura", "content": "v1", "tags": ["Python", "python"]}).json()
    assert n["tags"] == ["python"]
    n2 = client.patch(f"/api/notes/{n['id']}", json={"content": "v2", "base_revision": n["revision"]}).json()
    assert n2["revision"] == 2
    # Gravação com revisão antiga é recusada (protecção contra perda de conteúdo).
    r = client.patch(f"/api/notes/{n['id']}", json={"content": "x", "base_revision": 1})
    assert r.status_code == 409
    revs = client.get(f"/api/notes/{n['id']}/revisions").json()
    assert {r["content"] for r in revs} >= {"v1", "v2"}
    first = next(r for r in revs if r["content"] == "v1")
    restored = client.post(f"/api/notes/{n['id']}/revisions/{first['id']}/restore").json()
    assert restored["content"] == "v1"


def test_note_delete_requires_confirmation(client: TestClient) -> None:
    n = client.post("/api/notes", json={"title": "X"}).json()
    assert client.delete(f"/api/notes/{n['id']}").status_code == 428
    assert client.delete(f"/api/notes/{n['id']}", params={"confirm": True}).status_code == 204


def test_knowledge_graph_and_relations(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "Visão LGA"}).json()
    a = client.post(
        "/api/notes", json={"title": "YOLO", "kind": "concept", "in_knowledge_base": True, "project_id": p["id"]}
    ).json()
    b = client.post("/api/notes", json={"title": "Erro CUDA", "kind": "error", "in_knowledge_base": True}).json()
    r = client.post(
        "/api/relations",
        json={
            "source_type": "note",
            "source_id": b["id"],
            "target_type": "note",
            "target_id": a["id"],
            "label": "resolvido por",
        },
    )
    assert r.status_code == 201
    assert (
        client.post(
            "/api/relations",
            json={
                "source_type": "note",
                "source_id": b["id"],
                "target_type": "note",
                "target_id": a["id"],
                "label": "resolvido por",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/relations",
            json={"source_type": "note", "source_id": a["id"], "target_type": "note", "target_id": "inexistente"},
        ).status_code
        == 422
    )
    g = client.get("/api/knowledge/graph").json()
    assert len(g["nodes"]) == 3
    assert {e["label"] for e in g["edges"]} == {"projecto", "resolvido por"}
    rel = client.get("/api/relations", params={"entity_type": "note", "entity_id": a["id"]}).json()
    assert rel[0]["title"] == "Erro CUDA" and rel[0]["direction"] == "in"


def test_templates_project_from_template(client: TestClient) -> None:
    tpl = next(
        t
        for t in client.get("/api/checklists", params={"is_template": True}).json()
        if t["builtin_key"] == "api-development"
    )
    p = client.post("/api/projects/from-template", json={"template_id": tpl["id"], "name": "API Q360"}).json()
    tasks = client.get("/api/tasks", params={"project_id": p["id"]}).json()
    assert tasks["total"] == len(tpl["items"])
    lists = client.get("/api/checklists", params={"project_id": p["id"]}).json()
    assert len(lists) == 1 and lists[0]["source_template_id"] == tpl["id"]
    item = lists[0]["items"][0]
    client.patch(f"/api/checklist-items/{item['id']}", json={"done": True})
    assert client.get(f"/api/checklists/{lists[0]['id']}").json()["percent"] > 0
    # O modelo original não é afectado.
    assert all(not i["done"] for i in client.get(f"/api/checklists/{tpl['id']}").json()["items"])


def test_checklist_editing_and_duplicate(client: TestClient) -> None:
    c = client.post(
        "/api/checklists",
        json={"title": "Deploy", "is_template": True, "items": [{"text": "Testes", "section": "Antes"}]},
    ).json()
    c = client.post(f"/api/checklists/{c['id']}/items", json={"text": "Tag", "section": "Depois"}).json()
    assert len(c["items"]) == 2
    dup = client.post(f"/api/checklists/{c['id']}/duplicate", json={"as_template": True}).json()
    assert dup["is_template"] and dup["title"].endswith("(cópia)")
    r = client.post("/api/checklists", json={"title": "X", "is_template": True, "project_id": "abc"})
    assert r.status_code == 404


def test_search_fts(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "Detecção de matrículas", "description": "visão computacional"})
    client.post("/api/tasks", json={"title": "Treinar modelo YOLOv8"})
    client.post("/api/notes", json={"title": "Notas FastAPI", "content": "dependências com yield"})
    res = client.get("/api/search", params={"q": "visao"}).json()  # sem acento → remove_diacritics
    assert res["engine"] == "fts5"
    assert res["hits"][0]["entity_type"] == "project"
    assert res["hits"][0]["route"].startswith("/projects/")
    assert client.get("/api/search", params={"q": "yolo"}).json()["hits"][0]["entity_type"] == "task"
    assert client.get("/api/search", params={"q": "yield"}).json()["hits"][0]["entity_type"] == "note"
    # Sintaxe FTS maliciosa é neutralizada.
    assert client.get("/api/search", params={"q": '"; DROP TABLE tasks; NEAR('}).status_code == 200
    assert client.get("/api/search", params={"q": "yolo", "types": ["note"]}).json()["hits"] == []


def test_search_reflects_updates_and_deletes(client: TestClient) -> None:
    t = client.post("/api/tasks", json={"title": "Antigo"}).json()
    client.patch(f"/api/tasks/{t['id']}", json={"title": "Renovado"})
    assert client.get("/api/search", params={"q": "antigo"}).json()["hits"] == []
    assert len(client.get("/api/search", params={"q": "renovado"}).json()["hits"]) == 1
    client.delete(f"/api/tasks/{t['id']}", params={"confirm": True})
    assert client.get("/api/search", params={"q": "renovado"}).json()["hits"] == []


def test_commands(client: TestClient) -> None:
    r = client.post("/api/commands", json={"text": "tarefa Rever PR !alta @amanhã"}).json()
    assert r["kind"] == "created"
    t = client.get(f"/api/tasks/{r['entity_id']}").json()
    assert t["title"] == "Rever PR" and t["priority"] == "high" and t["due_at"]
    assert client.post("/api/commands", json={"text": "ir para agenda"}).json()["route"] == "/agenda"
    r = client.post("/api/commands", json={"text": "concluir Rever"}).json()
    assert r["kind"] == "result"
    assert client.get(f"/api/tasks/{t['id']}").json()["status"] == "done"
    assert client.post("/api/commands", json={"text": "xyz"}).json()["kind"] == "unknown"
    s = client.post("/api/commands", json={"text": "pesquisar Rever"}).json()
    assert s["kind"] == "search" and s["hits"][0]["route"].startswith("/tasks/")


def test_agenda_and_reviews(client: TestClient) -> None:
    r = client.post(
        "/api/events",
        json={"title": "Reunião", "start_at": "2026-10-20T09:00:00+01:00", "end_at": "2026-10-20T10:00:00+01:00"},
    )
    assert r.status_code == 201
    bad = client.post(
        "/api/events",
        json={"title": "X", "start_at": "2026-10-20T10:00:00+01:00", "end_at": "2026-10-20T09:00:00+01:00"},
    )
    assert bad.status_code == 422
    client.post("/api/tasks", json={"title": "Entregar", "due_at": "2026-10-21T15:00:00+01:00"})
    a = client.get("/api/agenda", params={"start": "2026-10-19", "days": 7}).json()
    assert len(a["events"]) == 1 and len(a["tasks"]) == 1
    rv = client.get("/api/reviews/weekly", params={"day": "2026-10-22"}).json()
    assert rv["review"]["period_start"] == "2026-10-19"  # segunda-feira
    up = client.put("/api/reviews/daily/2026-10-22", json={"goals": [{"text": "Fechar API"}], "closed": True}).json()
    assert up["closed_at"] and up["goals"][0]["text"] == "Fechar API"
