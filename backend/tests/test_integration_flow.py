"""Fluxo completo exigido (secção 13): criar → concluir → métricas → pesquisa → automação →
backup → restauro em base de teste → reinício com persistência."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TOKEN, make_settings
from uanji.main import create_app
from uanji.services.vault import MemoryStore


def test_end_to_end(client: TestClient, app, data_dir) -> None:  # type: ignore[no-untyped-def]
    # 1. Projecto
    p = client.post("/api/projects", json={"name": "Plataforma SkyLearn", "status": "active"}).json()
    # 2. Tarefas associadas
    t1 = client.post("/api/tasks", json={"title": "Configurar autenticação", "project_id": p["id"]}).json()
    client.post("/api/tasks", json={"title": "Escrever testes", "project_id": p["id"]})
    # 3. Nota ligada ao projecto
    client.post(
        "/api/notes",
        json={
            "title": "Decisão: JWT",
            "kind": "decision",
            "project_id": p["id"],
            "content": "Usar tokens de curta duração",
        },
    )
    before = client.get("/api/dashboard").json()["counters"]
    # 4. Concluir tarefa
    client.post(f"/api/tasks/{t1['id']}/status", json={"status": "done"})
    # 5. Métricas actualizadas
    after = client.get("/api/dashboard").json()
    assert after["counters"]["done_today"] == before["done_today"] + 1
    assert after["counters"]["pending_tasks"] == before["pending_tasks"] - 1
    assert client.get(f"/api/projects/{p['id']}").json()["progress"]["percent"] == 50
    m = client.get("/api/metrics").json()
    assert m["totals"]["done"] == 1 and m["done_by_project"][0]["project"] == "Plataforma SkyLearn"
    # 6. Pesquisa
    kinds = {h["entity_type"] for h in client.get("/api/search", params={"q": "JWT"}).json()["hits"]}
    assert "note" in kinds
    # 7. Automação interna
    a = client.post(
        "/api/automations",
        json={
            "name": "Resumo",
            "enabled": True,
            "definition": {
                "trigger": {"type": "manual"},
                "steps": [
                    {"id": "r", "action": "generate_summary", "params": {"scope": "today", "project_id": p["id"]}}
                ],
            },
        },
    ).json()
    run = client.post(f"/api/automations/{a['id']}/run").json()
    assert run["status"] == "success" and run["steps"][0]["output"]["done"] == 1
    # 8. Backup
    b = client.post("/api/backups").json()
    # 9. Restauro numa base de dados de teste
    tr = client.post(f"/api/backups/{b['filename']}/test-restore").json()
    assert tr["counts"]["projects"] == 1 and tr["counts"]["tasks"] == 2
    # 10. Reinício: nova instância sobre o mesmo directório de dados
    app.state.database.dispose()
    app2 = create_app(make_settings(data_dir), secret_store=MemoryStore())
    with TestClient(app2, headers={"Authorization": f"Bearer {TOKEN}"}) as c2:
        proj = c2.get(f"/api/projects/{p['id']}").json()
        assert proj["name"] == "Plataforma SkyLearn" and proj["progress"]["tasks_done"] == 1
        assert c2.get("/api/notes").json()["total"] >= 2
        assert len(c2.get(f"/api/automations/{a['id']}/runs").json()) == 1
        assert len(c2.get("/api/checklists", params={"is_template": True}).json()) == 7
    app2.state.database.dispose()
