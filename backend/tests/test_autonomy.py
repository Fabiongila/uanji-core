# ruff: noqa: F811  (a fixture «voice» é importada de test_assistant_voice)
"""Autonomia: monitor de actividade, iniciativa do assistente, acções no sistema e aparência.

O sistema operativo é simulado (sonda de actividade, execução de processos); nada é aberto,
fechado ou executado de verdade nestes testes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from uanji.activity import insights
from uanji.activity import monitor as activity
from uanji.assistant import proactive
from uanji.system import macos

from .test_assistant_voice import FakeMic, FakeSpeaker, FakeSTT, say, voice  # noqa: F401

T0 = datetime(2026, 10, 29, 8, 0, tzinfo=UTC)  # 09:00 em Luanda


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw: float) -> None:
        self.t += timedelta(**kw)


class Probe:
    def __init__(self) -> None:
        self.sample = activity.Sample("Code", "com.microsoft.VSCode", context="Q360-Linha-Saude-backend")

    def __call__(self, capture_titles: bool) -> activity.Sample:
        return self.sample


def enable_activity(client: TestClient) -> None:
    r = client.patch("/api/settings", json={"values": {"activity": {"enabled": False, "sample_seconds": 15}}})
    assert r.status_code == 200
    from uanji import runtime
    from uanji.services.common import put_setting

    with runtime.get_database().session() as db:
        put_setting(db, "activity", {**r.json()["activity"], "enabled": True})


# --------------------------------------------------------------------------- monitor e padrões


def test_categories_and_project_matching() -> None:
    assert activity.categorize("Code", "com.microsoft.VSCode") == "desenvolvimento"
    assert activity.categorize("zoom.us") == "reunioes"
    assert activity.categorize("Google Chrome") == "navegacao"
    projects = [("p1", "API Q360 Linha Saúde"), ("p2", "UANJI CORE"), ("p3", "Gestão Escolar")]
    assert activity.match_project("Q360-Linha-Saude-backend", projects) == "p1"
    assert activity.match_project("uanji-core", projects) == "p2"
    assert activity.match_project("Find-me", projects) is None


def test_monitor_groups_samples_ignores_idle_and_excluded(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "API Q360 Linha Saúde", "status": "active"})
    clock, probe = Clock(T0), Probe()
    m = activity.ActivityMonitor(probe=probe, clock=clock)
    cfg = {"idle_seconds": 300, "excluded_apps": ["1Password"], "capture_titles": False}
    for _ in range(5):  # 4 × 15 s no VS Code
        m.tick(cfg)
        clock.advance(seconds=15)
    probe.sample = activity.Sample("Google Chrome", "com.google.Chrome")
    m.tick(cfg)
    clock.advance(seconds=30)
    m.tick(cfg)
    probe.sample = activity.Sample("1Password", "com.1password")  # excluída: não registada
    clock.advance(seconds=15)
    m.tick(cfg)
    probe.sample = activity.Sample("Google Chrome", idle_seconds=900)  # ausente
    clock.advance(minutes=15)
    m.tick(cfg)
    assert m.state.active_since is None
    probe.sample = activity.Sample("Code", "com.microsoft.VSCode", context="Q360-Linha-Saude-backend")
    clock.advance(seconds=15)
    m.tick(cfg)
    assert m.state.returned_after >= 15 * 60

    sessions = client.get("/api/activity/sessions", params={"day": "2026-10-29"}).json()
    assert [s["app"] for s in sessions] == ["Code", "Google Chrome", "Code"]
    assert sessions[0]["seconds"] == 60 and sessions[0]["project_id"] and sessions[1]["seconds"] == 30
    assert all(s["app"] != "1Password" for s in sessions)
    assert m.state.switches_in(60, clock()) == 2


def test_summary_and_patterns_from_real_sessions(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    from uanji.models import ActivitySession

    with app.state.database.session() as db:
        for d in range(1, 5):
            start = T0 - timedelta(days=d)
            db.add(
                ActivitySession(
                    app="Code",
                    category="desenvolvimento",
                    started_at=start,
                    ended_at=start + timedelta(hours=2),
                    seconds=7200,
                )
            )
        db.add(
            ActivitySession(
                app="Code",
                category="desenvolvimento",
                context="uanji-core",
                started_at=T0,
                ended_at=T0 + timedelta(minutes=90),
                seconds=5400,
            )
        )
    with app.state.database.session() as db:
        s = insights.summarize(db, T0.date())
        p = insights.patterns(db)
    assert s["active_seconds"] == 5400 and s["apps"][0]["app"] == "Code"
    assert "1 h 30 min" in insights.summary_sentence(s)
    assert p["days_with_data"] >= 3 and p["avg_start"] == "09:00"
    assert "começou em média às 09:00" in insights.patterns_sentence(p)


def test_activity_disabled_says_so_and_never_invents(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    out = say(client, "o que tenho estado a fazer hoje?")
    assert "monitor de actividade está desligado" in out["reply"]
    assert client.get("/api/activity/status").json()["enabled"] is False
    assert client.delete("/api/activity").status_code == 428


# --------------------------------------------------------------------------- iniciativa


def deliveries() -> tuple[list[proactive.Nudge], Any]:
    got: list[proactive.Nudge] = []

    def deliver(n: proactive.Nudge) -> bool:
        got.append(n)
        return True

    return got, deliver


def test_morning_briefing_once_with_offer_and_yes_runs_it(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    svc, _, speaker = voice
    client.post("/api/tasks", json={"title": "Corrigir login", "priority": "critical"})
    clock = Clock(T0)
    engine = proactive.ProactiveEngine(deliver=svc.proactive, clock=clock, live=lambda: None)
    n = engine.tick()
    assert n is not None and n.rule == "morning"
    assert "Bom dia" in n.text and "Corrigir login" in n.text and n.text.endswith("Quer que leia as prioridades?")
    # Falou sem ninguém carregar em nada.
    import time

    for _ in range(100):
        if speaker.spoken:
            break
        time.sleep(0.02)
    assert speaker.spoken and speaker.spoken[-1] == n.text
    # Também fica nas notificações internas, e não se repete.
    assert any(x["category"] == "assistant" for x in client.get("/api/notifications").json())
    clock.advance(hours=2)
    assert engine.tick() is None or engine.last_at == clock()
    # «sim» na mesma conversa executa a oferta.
    out = say(client, "sim", svc.conversation_id)
    assert out["report"]["kind"] == "next_steps" and "Corrigir login" in out["reply"]


def test_rules_respect_quiet_hours_gap_and_urgency(client: TestClient) -> None:
    got, deliver = deliveries()
    clock = Clock(datetime(2026, 10, 29, 22, 30, tzinfo=UTC))  # 23:30 em Luanda: silêncio
    engine = proactive.ProactiveEngine(deliver=deliver, clock=clock, live=lambda: None)
    client.post(
        "/api/tasks", json={"title": "Entregar relatório", "due_at": (clock.t + timedelta(minutes=30)).isoformat()}
    )
    assert engine.tick() is None and not got
    clock.t = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)  # 10:00
    client.post(
        "/api/tasks", json={"title": "Enviar proposta", "due_at": (clock.t + timedelta(minutes=40)).isoformat()}
    )
    first = engine.tick()
    assert first is not None and first.rule == "deadlines" and "Enviar proposta" in first.text
    second = engine.tick()  # o bom-dia espera pelo intervalo mínimo; prazos não
    assert second is None or second.rule in proactive.URGENT
    clock.advance(minutes=25)
    third = engine.tick()
    assert third is not None and third.rule == "morning"


def test_breaks_context_switching_and_project_suggestion(client: TestClient) -> None:
    client.patch("/api/settings", json={"values": {"proactive": {"rules": {"morning": False}}}})
    got, deliver = deliveries()
    clock = Clock(T0)
    live = activity.LiveState(
        app="Code",
        category="desenvolvimento",
        context="Find-me",
        since=T0 - timedelta(minutes=40),
        active_since=T0 - timedelta(minutes=40),
    )
    engine = proactive.ProactiveEngine(deliver=deliver, clock=clock, live=lambda: live)
    n = engine.tick()
    assert (
        n is not None
        and n.rule == "suggestions"
        and "Find-me" in n.text
        and n.offer == ("create_project", {"name": "Find-me"})
    )
    clock.advance(minutes=60)  # 100 min sem pausa
    n2 = engine.tick()
    assert n2 is not None and n2.rule == "breaks"
    clock.advance(minutes=21)
    for i in range(30):
        live.switches.append(clock() - timedelta(seconds=i * 10))
    n3 = engine.tick()
    assert n3 is not None and n3.rule == "context_switch" and n3.offer == ("start_focus", {})
    live.idle_seconds = 600  # ausente: não fala
    clock.advance(minutes=30)
    assert engine.tick() is None


def test_proactive_waits_while_busy_and_disabled(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    svc, _, _ = voice
    svc.state = "listening"
    engine = proactive.ProactiveEngine(deliver=svc.proactive, clock=Clock(T0), live=lambda: None)
    assert engine.tick() is None  # ocupado: tenta depois
    svc.state = "off"
    client.patch("/api/settings", json={"values": {"proactive": {"enabled": False}}})
    assert engine.tick() is None


# --------------------------------------------------------------------------- sistema


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], timeout: float = 10.0, cwd: str | None = None) -> macos.RunResult:
        self.calls.append(args)
        return macos.RunResult(0, "ok\n", "")


@pytest.fixture
def runner(monkeypatch):  # type: ignore[no-untyped-def]
    r = FakeRunner()
    monkeypatch.setattr(macos, "runner", r)
    return r


def test_open_app_volume_url_and_quit_confirmation(client: TestClient, voice, runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    monkeypatch.setattr(
        macos,
        "installed_apps",
        lambda: [Path("/Applications/Visual Studio Code.app"), Path("/Applications/Google Chrome.app")],
    )
    out = say(client, "abre o VS Code")
    assert out["reply"] == "A abrir Visual Studio Code." and runner.calls[-1][:2] == ["/usr/bin/open", "-a"]
    out = say(client, "põe o volume a 30")
    assert "30%" in out["reply"] and "set volume output volume 30" in runner.calls[-1][-1]
    say(client, "pesquisa na web receitas de muamba")
    assert runner.calls[-1][1].startswith("https://www.google.com/search?q=receitas+de+muamba")
    out = say(client, "fecha o Chrome")
    assert out["awaiting"] == "confirmation"  # fechar pode perder trabalho
    out = say(client, "abre o Photoshop")
    assert out["error"] and "Photoshop" in out["reply"]


def test_shell_disabled_by_default_then_always_confirmed(client: TestClient, voice, runner) -> None:  # type: ignore[no-untyped-def]
    out = say(client, "corre o comando ls -la")
    assert out["awaiting"] == "confirmation" and out["actions"][0]["risk"] == "destructive"
    assert any("desligada" in d for d in out["actions"][0]["details"])
    done = say(client, "sim", out["conversation_id"])
    assert done["error"] and "desligada" in done["reply"] and runner.calls == []

    client.patch("/api/settings", json={"values": {"system": {"allow_shell": True}}})
    out = say(client, "corre o comando ls -la", out["conversation_id"])
    assert out["awaiting"] == "confirmation" and "Comando: ls -la" in out["actions"][0]["details"]
    done = say(client, "sim", out["conversation_id"])
    assert "terminou sem erros" in done["reply"] and runner.calls[-1] == ["/bin/zsh", "-c", "ls -la"]
    out = say(client, "corre o comando sudo rm -rf /")
    yes = say(client, "sim", out["conversation_id"])
    assert yes["error"] and "sudo" in yes["reply"] and runner.calls[-1] == ["/bin/zsh", "-c", "ls -la"]


def test_appearance_and_usage_settings(client: TestClient) -> None:
    r = client.patch(
        "/api/settings",
        json={
            "values": {
                "appearance": {
                    "theme": "light",
                    "accent": "violet",
                    "sidebar": "right",
                    "font_scale": 110,
                    "cards": [{"id": "tasks", "size": "l"}, {"id": "agenda", "hidden": True}],
                }
            }
        },
    )
    assert r.status_code == 200 and r.json()["appearance"]["cards"][1] == {"id": "agenda", "size": "m", "hidden": True}
    assert client.patch("/api/settings", json={"values": {"appearance": {"theme": "neon"}}}).status_code == 422
    assert client.patch("/api/settings", json={"values": {"appearance": {"font_scale": 300}}}).status_code == 422
    for _ in range(3):
        client.post("/api/usage", json={"area": "tasks"})
    u = client.post("/api/usage", json={"area": "notes"}).json()
    assert u["tasks"] > u["notes"] > 0
    assert client.post("/api/usage", json={"area": "../x"}).status_code == 422
