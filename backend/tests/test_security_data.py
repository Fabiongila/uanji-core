"""Cofre, backups/restauro, integrações (simuladas), assistente (fornecedor simulado) e definições."""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import zipfile

import httpx
from fastapi.testclient import TestClient

from uanji.assistant import core as assistant
from uanji.integrations import github
from uanji.logging_setup import redact

SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"


def test_vault_never_stores_value_in_db(client: TestClient, data_dir) -> None:  # type: ignore[no-untyped-def]
    e = client.post("/api/vault", json={"name": "GitHub", "service": "github", "value": SECRET}).json()
    assert "value" not in e and e["hint"] == "…6789"
    listed = client.get("/api/vault").json()
    assert SECRET not in json.dumps(listed)
    raw = (data_dir / "uanji.db").read_bytes()
    assert SECRET.encode() not in raw
    assert client.post(f"/api/vault/{e['id']}/reveal").json()["value"] == SECRET
    hist = client.get("/api/activity").json()
    assert all(SECRET not in h["summary"] for h in hist)
    # Acções sensíveis não aparecem no dashboard.
    assert all(a["entity_type"] != "secret" for a in client.get("/api/dashboard").json()["recent_activity"])
    assert client.delete(f"/api/vault/{e['id']}").status_code == 428
    assert client.delete(f"/api/vault/{e['id']}", params={"confirm": True}).status_code == 204
    assert client.get("/api/vault/status").json()["secure"] is False  # backend de testes identificado


def test_log_redaction() -> None:
    assert SECRET not in redact(f"token={SECRET}")
    assert SECRET not in redact(f"Authorization: Bearer {SECRET}")
    assert "[REDACTED]" in redact('{"api_key": "abc123"}')


def test_backup_verify_restore(client: TestClient, data_dir) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/vault", json={"name": "k", "value": SECRET})
    p = client.post("/api/projects", json={"name": "Antes do backup"}).json()
    b = client.post("/api/backups").json()
    assert b["filename"].endswith(".zip")
    with zipfile.ZipFile(data_dir / "backups" / b["filename"]) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["secrets_included"] is False
        assert SECRET.encode() not in z.read("uanji.db")
    v = client.post(f"/api/backups/{b['filename']}/verify").json()
    assert v["integrity"] == "ok" and v["counts"]["projects"] == 1
    t = client.post(f"/api/backups/{b['filename']}/test-restore").json()
    assert t["ok"] and t["counts"]["projects"] == 1

    client.post("/api/projects", json={"name": "Depois do backup"})
    r = client.post(f"/api/backups/{b['filename']}/restore", json={"confirm": False})
    assert r.status_code == 428  # exige confirmação
    r = client.post(f"/api/backups/{b['filename']}/restore", json={"confirm": True}).json()
    assert r["safety_backup"].startswith("uanji-backup-")
    names = [x["name"] for x in client.get("/api/projects").json()["items"]]
    assert names == ["Antes do backup"]
    assert client.get(f"/api/projects/{p['id']}").status_code == 200
    # O histórico de backups inclui o backup de segurança, mesmo após restauro.
    files = [x["filename"] for x in client.get("/api/backups").json()["items"]]
    assert r["safety_backup"] in files and b["filename"] in files


def test_backup_rejects_tampered_and_bad_names(client: TestClient, data_dir) -> None:  # type: ignore[no-untyped-def]
    b = client.post("/api/backups").json()
    path = data_dir / "backups" / b["filename"]
    with zipfile.ZipFile(path) as z:
        manifest, db = z.read("manifest.json"), bytearray(z.read("uanji.db"))
    db[200] ^= 0xFF
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", manifest)
        z.writestr("uanji.db", bytes(db))
    r = client.post("/api/backups/import", files={"file": ("x.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422 and "SHA-256" in r.json()["error"]["message"]
    assert client.post("/api/backups/..%2F..%2Fetc%2Fpasswd/verify").status_code in (404, 422)
    assert client.post("/api/backups/../x/verify").status_code in (404, 422)
    r = client.post("/api/backups/import", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert r.status_code == 422


def test_import_validates_then_restores(client: TestClient, data_dir) -> None:  # type: ignore[no-untyped-def]
    client.post("/api/tasks", json={"title": "No backup"})
    b = client.post("/api/backups").json()
    content = (data_dir / "backups" / b["filename"]).read_bytes()
    client.post("/api/tasks", json={"title": "Posterior"})
    r = client.post("/api/backups/import", files={"file": ("b.zip", content, "application/zip")}).json()
    assert r["validated"] and r["counts"]["tasks"] == 1
    assert client.get("/api/tasks").json()["total"] == 2  # só validou
    client.post("/api/backups/import", params={"confirm": True}, files={"file": ("b.zip", content, "application/zip")})
    assert [t["title"] for t in client.get("/api/tasks").json()["items"]] == ["No backup"]


def test_export_excludes_secret_values(client: TestClient) -> None:
    client.post("/api/vault", json={"name": "k", "value": SECRET})
    client.post("/api/projects", json={"name": "Exportado"})
    r = client.get("/api/export")
    assert SECRET not in r.text
    assert r.json()["tables"]["projects"][0]["name"] == "Exportado"


def _gh_transport(status: int = 200):  # type: ignore[no-untyped-def]
    def handler(req: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"message": "x"})
        path = req.url.path
        if path == "/user":
            assert req.headers["authorization"] == f"Bearer {SECRET}"
            return httpx.Response(200, json={"login": "fabio", "name": "Fábio"})
        if path == "/repos/foo/bar":
            return httpx.Response(
                200,
                json={"full_name": "foo/bar", "stargazers_count": 3, "open_issues_count": 1, "default_branch": "main"},
            )
        if path.endswith("/commits"):
            return httpx.Response(
                200, json=[{"sha": "abcdef123", "commit": {"message": "init\n\nx", "author": {"name": "F"}}}]
            )
        if path.endswith("/pulls"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_github_integration(client: TestClient) -> None:
    status = client.get("/api/integrations").json()[0]
    assert status["status"] == "not_configured"
    github.transport = _gh_transport()
    github._cache.clear()
    try:
        sec = client.post("/api/vault", json={"name": "gh", "value": SECRET}).json()
        r = client.put("/api/integrations/github", json={"secret_id": sec["id"]}).json()
        assert r["status"] == "connected" and r["config"]["login"] == "fabio"
        repo = client.post("/api/integrations/github/repo", json={"url": "https://github.com/foo/bar"}).json()
        assert repo["repo"]["full_name"] == "foo/bar" and repo["commits"][0]["message"] == "init"
        assert repo["source"] == "api.github.com"
        bad = client.post("/api/integrations/github/repo", json={"url": "https://gitlab.com/foo/bar"})
        assert bad.status_code == 422
        github.transport = _gh_transport(401)
        r = client.post("/api/integrations/github/test").json()
        assert r["status"] == "error" and "401" in r["last_error"]
    finally:
        github.transport = None
        github._cache.clear()


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def turn(self, system, messages, tools):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 1:
            return assistant.ProviderTurn(
                "",
                [
                    {"id": "c1", "name": "list_tasks", "input": {"due": "overdue"}},
                    {"id": "c2", "name": "propose_create_task", "input": {"title": "Sugerida pela IA"}},
                ],
                "tool_use",
                [{"type": "text", "text": "..."}],
            )
        # Os resultados das ferramentas são marcados como dados não confiáveis.
        results = messages[-1]["content"]
        assert "untrusted_data" in results[0]["content"]
        assert "pending_user_confirmation" in results[1]["content"]
        return assistant.ProviderTurn("Propus uma tarefa.", [], "end_turn", [])


def test_assistant_requires_provider(client: TestClient) -> None:
    s = client.get("/api/assistant/status").json()
    assert s["configured"] is False
    r = client.post("/api/assistant/chat", json={"message": "olá"})
    assert r.status_code == 503


def test_assistant_tools_need_confirmation(client: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    with app.state.database.session() as db:
        out = assistant.chat(db, [], "o que está atrasado?", provider=FakeProvider())
    assert out["consulted"][0]["tool"] == "list_tasks"
    action = out["proposed_actions"][0]
    assert client.get("/api/tasks").json()["total"] == 0  # nada executado sem confirmação
    r = client.post(f"/api/assistant/actions/{action['id']}", json={"approve": True}).json()
    assert r["status"] == "confirmed"
    assert client.get("/api/tasks").json()["items"][0]["title"] == "Sugerida pela IA"
    again = client.post(f"/api/assistant/actions/{action['id']}", json={"approve": True})
    assert again.status_code == 422


def test_settings_patch_validated(client: TestClient) -> None:
    s = client.patch("/api/settings", json={"values": {"notifications": {"deadline_hours": 48}}}).json()
    assert s["notifications"]["deadline_hours"] == 48 and s["notifications"]["enabled"] is True
    assert client.patch("/api/settings", json={"values": {"evil": 1}}).status_code == 422
    assert client.patch("/api/settings", json={"values": {"timezone": "Marte/Base"}}).status_code == 422


def test_diagnostics_no_secrets(client: TestClient) -> None:
    client.post("/api/vault", json={"name": "k", "value": SECRET})
    logging.getLogger("teste").warning("token=%s", SECRET)
    d = client.get("/api/diagnostics").json()
    assert d["schema_revision"] == d["schema_head"] and d["fts5_available"]
    assert SECRET not in json.dumps(d)
    assert SECRET not in json.dumps(client.get("/api/diagnostics/logs").json())


def test_notifications_reminders_dedupe(client: TestClient, app) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime, timedelta

    from uanji.services import notifications

    client.post(
        "/api/tasks", json={"title": "Atrasada", "due_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}
    )
    client.post(
        "/api/tasks", json={"title": "Em breve", "due_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat()}
    )
    with app.state.database.session() as db:
        notifications.generate_reminders(db)
        notifications.generate_reminders(db)
    cats = [n["category"] for n in client.get("/api/notifications").json()]
    assert cats.count("overdue") == 1 and cats.count("deadline") == 1
    client.patch("/api/settings", json={"values": {"notifications": {"categories": {"overdue": False}}}})
    assert client.post("/api/notifications/read", json={}).json()["updated"] >= 2
    assert client.get("/api/notifications/summary").json()["unread"] == 0
    # Nativas desligadas por omissão.
    assert client.get("/api/notifications/native").json() == []


def test_sqlite_fk_enforced(data_dir, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/api/tasks", json={"title": "x", "project_id": "nao-existe"})
    assert r.status_code == 404
    conn = sqlite3.connect(data_dir / "uanji.db")
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
