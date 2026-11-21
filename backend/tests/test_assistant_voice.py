"""Assistente (interpretação local, ferramentas, confirmações, relatórios) e serviço de voz.

O microfone, o STT e o TTS são substituídos por simulações: os testes verificam o fluxo,
os estados e as garantias (nada executado sem confirmação, microfone fechado quando a
escuta está desligada, etc.). Os testes com hardware real estão documentados em docs/VOICE.md.
"""

from __future__ import annotations

import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from uanji.assistant import conversation, core
from uanji.assistant.intents import Parser
from uanji.voice import capture, tts
from uanji.voice import service as voice_service
from uanji.voice.dsp import FRAME_SAMPLES, SAMPLE_RATE
from uanji.voice.wake import Template

from .conftest import make_settings

# --------------------------------------------------------------------------- utilitários


def say(client: TestClient, text: str, cid: str | None = None) -> dict[str, Any]:
    r = client.post("/api/assistant/message", json={"text": text, "conversation_id": cid})
    assert r.status_code == 200, r.text
    return r.json()


def wait_for(cond: Callable[[], bool], timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("condição não satisfeita a tempo")


def tone(ms: int, amp: float = 0.3) -> bytes:
    t = np.arange(int(SAMPLE_RATE * ms / 1000)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * t) * amp * 32767).astype(np.int16).tobytes()


def silence(ms: int) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * ms / 1000)


class FakeMic:
    instances: list[FakeMic] = []

    def __init__(self) -> None:
        self.active = False
        self.device = {"name": "Microfone simulado", "samplerate": SAMPLE_RATE}
        self._cb: Callable[[bytes], None] | None = None
        FakeMic.instances.append(self)

    def start(self, on_frame: Callable[[bytes], None]) -> None:
        self.active = True
        self._cb = on_frame

    def stop(self) -> None:
        self.active = False

    def feed(self, pcm: bytes) -> None:
        step = FRAME_SAMPLES * 2
        for i in range(0, len(pcm), step):
            if self.active and self._cb:
                self._cb(pcm[i : i + step])


class FakeRecognizer:
    def __init__(self, stt: FakeSTT) -> None:
        self.stt = stt

    def accept(self, pcm: bytes) -> str:
        return self.stt.next_text[:5]

    def final(self) -> str:
        return self.stt.next_text


class FakeSTT:
    name = "fake"
    local = True

    def __init__(self) -> None:
        self.next_text = ""
        self.installed = True

    def status(self) -> dict[str, Any]:
        return {"engine": "fake", "local": True, "model_installed": self.installed}

    def ready(self) -> bool:
        return self.installed

    def load(self) -> None:
        pass

    def recognizer(self) -> FakeRecognizer:
        return FakeRecognizer(self)


class FakeSpeaker(tts.Speaker):
    def __init__(self) -> None:
        super().__init__()
        self.spoken: list[str] = []
        self.stopped = 0

    def speak(self, text: str, voice: str, rate: int = 185, volume: float = 0.9, block: bool = False) -> None:
        self.spoken.append(text)
        self._sentences = tts.split_sentences(text)
        self._index = 0
        self._interrupted = True
        if self.on_state:
            self.on_state(True)
            self.on_state(False)

    def stop(self) -> bool:
        self.stopped += 1
        return False


@pytest.fixture
def voice(app, monkeypatch):  # type: ignore[no-untyped-def]
    FakeMic.instances = []
    monkeypatch.setattr(capture, "mic_permission", lambda: "authorized")
    monkeypatch.setattr(tts, "available", lambda: True)
    stt, speaker = FakeSTT(), FakeSpeaker()
    svc = voice_service.VoiceService(app.state.settings.data_dir, mic_factory=FakeMic, stt=stt, speaker=speaker)
    svc.reload_settings()
    voice_service.set_service(svc)
    yield svc, stt, speaker
    voice_service.set_service(None)


def project(client: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    r = client.post("/api/projects", json={"name": name, "status": "active", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def task(client: TestClient, title: str, **extra: Any) -> dict[str, Any]:
    r = client.post("/api/tasks", json={"title": title, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- interpretação local


@pytest.mark.parametrize(
    ("text", "tool", "params"),
    [
        ("UAJI, quais são as minhas tarefas prioritárias de hoje?", "build_report", {"kind": "next_steps"}),
        ("Qual dos meus projectos está mais atrasado?", "build_report", {"kind": "projects"}),
        (
            "Cria uma tarefa para rever a autenticação do Q360.",
            "create_task",
            {"title": "Rever a autenticação do Q360"},
        ),
        ("Resume o trabalho que fiz hoje.", "build_report", {"kind": "daily"}),
        ("Mostra-me as automações que falharam.", "list_automation_runs", {"status": "failed", "period": "week"}),
        ("Prepara a minha revisão semanal.", "build_report", {"kind": "weekly"}),
        ("Abre o projecto Gestão Escolar.", "navigate", {"target": "o projecto Gestão Escolar"}),
        ("UAJI, faz o relatório do meu dia.", "build_report", {"kind": "daily"}),
        (
            "cria tarefa Rever PR urgente para amanhã",
            "create_task",
            {"title": "Rever PR", "due": "amanha", "priority": "critical"},
        ),
        ("passa a tarefa Deploy para em curso", "update_task_status", {"task": "Deploy", "status": "in_progress"}),
        ("apaga o projecto Teste", "delete_project", {"project": "Teste"}),
    ],
)
def test_parser_examples(text: str, tool: str, params: dict[str, Any]) -> None:
    i = Parser(["UAJI"]).parse(text)
    assert (i.kind, i.tool, i.params) == ("tool", tool, params)


def test_parser_context_and_slots() -> None:
    p = Parser(["UAJI"])
    assert p.parse("Explica-me o que está a bloquear este projecto.").needs_project_context
    idea = p.parse("Regista esta ideia nas minhas notas.")
    assert idea.tool == "create_note" and idea.missing == "title"
    assert p.parse("qual é a capital de França?").kind == "unknown"
    assert p.parse("repete").control == "repeat"


# --------------------------------------------------------------------------- acções reais


def test_create_task_by_command_is_real(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    q = project(client, "Q360")
    out = say(client, "Cria uma tarefa para rever a autenticação no projecto Q360 para amanhã")
    assert not out["error"] and out["executed"][0]["tool"] == "create_task"
    tasks = client.get("/api/tasks").json()["items"]
    assert [t["title"] for t in tasks] == ["Rever a autenticação"]
    assert tasks[0]["project_id"] == q["id"] and tasks[0]["due_at"]
    assert "Tarefa criada" in out["reply"]


def test_queries_use_real_data_and_never_invent(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    empty = say(client, "faz o relatório do meu dia")
    assert empty["report"]["kind"] == "daily"
    kinds = [s["kind"] for s in empty["report"]["sections"]]
    assert "facts" in kinds and "unavailable" in kinds
    assert "Concluiu 0 tarefas" in empty["report"]["sections"][0]["items"][0]

    task(client, "Corrigir login", priority="critical")
    done = task(client, "Escrever testes")
    client.post(f"/api/tasks/{done['id']}/status", json={"status": "done"})
    out = say(client, "quais são as minhas tarefas prioritárias de hoje?")
    assert "Corrigir login" in out["reply"]
    daily = say(client, "resume o trabalho que fiz hoje")
    facts = daily["report"]["sections"][0]["items"]
    assert any("Escrever testes" in f for f in facts)


def test_weekly_review_opens_planning(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    out = say(client, "Prepara a minha revisão semanal.")
    assert out["report"]["kind"] == "weekly" and out["navigate"] == "/planning"


def test_most_delayed_project(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    project(client, "Atrasado", due_date="2020-01-01", start_date="2019-01-01")
    project(client, "Em dia")
    out = say(client, "Qual dos meus projectos está mais atrasado?")
    derived = next(s for s in out["report"]["sections"] if s["kind"] == "derived")
    assert "Atrasado" in derived["items"][0]


def test_destructive_requires_confirmation_by_voice(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    task(client, "Tarefa temporária")
    out = say(client, "apaga a tarefa temporária")
    assert out["awaiting"] == "confirmation"
    assert out["actions"][0]["risk"] == "destructive"
    assert any("não pode ser desfeita" in d for d in out["actions"][0]["details"])
    assert client.get("/api/tasks").json()["total"] == 1  # nada eliminado ainda
    cid = out["conversation_id"]
    no = say(client, "não", cid)
    assert "Nada foi alterado" in no["reply"]
    assert client.get("/api/tasks").json()["total"] == 1

    out = say(client, "apaga a tarefa temporária", cid)
    yes = say(client, "sim", cid)
    assert yes["actions"][0]["status"] == "confirmed" and "eliminada" in yes["reply"]
    assert client.get("/api/tasks").json()["total"] == 0


def test_updates_confirm_by_default_and_setting_applies(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    task(client, "Rever PR")
    out = say(client, "conclui a tarefa rever PR")
    assert out["awaiting"] == "confirmation"
    r = client.post(f"/api/assistant/actions/{out['actions'][0]['id']}", json={"approve": True}).json()
    assert r["status"] == "confirmed"
    assert client.get("/api/tasks").json()["items"][0]["status"] == "done"

    client.patch("/api/settings", json={"values": {"assistant": {"confirm_creates": True}}})
    out = say(client, "cria uma tarefa Nova coisa")
    assert out["awaiting"] == "confirmation"
    assert client.get("/api/tasks", params={"q": "Nova"}).json()["total"] == 0


def test_ambiguity_slots_and_context(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    project(client, "Gestão Escolar", blocked_reason="")
    project(client, "Gestão Financeira")
    out = say(client, "abre o projecto gestão")
    assert out["awaiting"] == "choice"
    cid = out["conversation_id"]
    chosen = say(client, "o primeiro", cid)
    assert chosen["navigate"].startswith("/projects/")
    blockers = say(client, "o que está a bloquear este projecto?", cid)
    assert "Gestão" in blockers["reply"] and not blockers["error"]

    ask = say(client, "Regista esta ideia nas minhas notas.", cid)
    assert ask["awaiting"] == "slot" and "ideia" in ask["reply"]
    saved = say(client, "usar Vosk para reconhecimento local", cid)
    assert "Ideia registada" in saved["reply"]
    notes = client.get("/api/notes").json()["items"]
    assert notes[0]["kind"] == "idea" and "Vosk" in notes[0]["title"]

    again = say(client, "repete", cid)
    assert again["reply"] == saved["reply"] and again["control"] == "repeat"


def test_unknown_without_ai_and_ai_errors(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    out = say(client, "qual é a capital de França?")
    assert out["engine"] == "none" and "Não percebi" in out["reply"]

    class Failing:
        name = "fake"

        def turn(self, *a: Any) -> core.ProviderTurn:
            from uanji.errors import ExternalServiceError

            raise ExternalServiceError("Sem ligação ao fornecedor de IA.")

    client.patch("/api/settings", json={"values": {"assistant": {"provider": "anthropic", "secret_id": "x"}}})
    svc, _, _ = voice
    svc.assistant = conversation.Assistant(provider=Failing())  # type: ignore[arg-type]
    out = say(client, "qual é a capital de França?")
    assert out["error"] and "Sem ligação" in out["reply"] and out["engine"] == "ai"
    # Os pedidos locais continuam a funcionar sem Internet.
    assert not say(client, "cria tarefa Funciona offline")["error"]


def test_ai_write_always_needs_confirmation(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    class Proposer:
        name = "fake"
        calls = 0

        def turn(self, system: str, messages: list[Any], tools: list[Any]) -> core.ProviderTurn:
            Proposer.calls += 1
            assert "Forma de tratamento" in system
            if Proposer.calls == 1:
                return core.ProviderTurn(
                    "", [{"id": "1", "name": "create_task", "input": {"title": "Da IA"}}], "tool_use", []
                )
            return core.ProviderTurn("Propus a tarefa.", [], "end_turn", [])

    client.patch("/api/settings", json={"values": {"assistant": {"provider": "anthropic", "secret_id": "x"}}})
    svc, _, _ = voice
    svc.assistant = conversation.Assistant(provider=Proposer())  # type: ignore[arg-type]
    out = say(client, "organiza-me a semana com uma tarefa")
    assert out["awaiting"] == "confirmation" and client.get("/api/tasks").json()["total"] == 0
    say(client, "sim", out["conversation_id"])
    assert client.get("/api/tasks").json()["items"][0]["title"] == "Da IA"


# --------------------------------------------------------------------------- definições, tratamento e histórico


def test_persona_settings_validation_and_persistence(client: TestClient, data_dir: Path, voice) -> None:  # type: ignore[no-untyped-def]
    assert client.patch("/api/settings", json={"values": {"persona": {"address": "robot"}}}).status_code == 422
    assert client.patch("/api/settings", json={"values": {"voice": {"rate": 5}}}).status_code == 422
    r = client.patch(
        "/api/settings",
        json={"values": {"persona": {"address": "feminine"}, "voice": {"voice": "Luciana", "rate": 200}}},
    )
    assert r.status_code == 200
    assert say(client, "olá")["reply"].startswith("Estou aqui, senhora.")
    client.patch("/api/settings", json={"values": {"persona": {"address": "custom", "custom": "Chefe"}}})
    assert "Chefe" in say(client, "olá")["reply"]
    client.patch("/api/settings", json={"values": {"persona": {"address": "neutral"}}})
    assert say(client, "olá")["reply"] == "Estou aqui. Em que posso ajudar?"

    # Persistência depois de reiniciar a aplicação (mesma pasta de dados).
    from uanji.main import create_app
    from uanji.services.vault import MemoryStore

    from .conftest import TOKEN

    app2 = create_app(make_settings(data_dir), secret_store=MemoryStore())
    with TestClient(app2, headers={"Authorization": f"Bearer {TOKEN}"}) as c2:
        s = c2.get("/api/settings").json()
        assert s["voice"]["voice"] == "Luciana" and s["voice"]["rate"] == 200
    app2.state.database.dispose()


def test_history_retention(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    out = say(client, "olá")
    h = client.get("/api/assistant/history", params={"conversation_id": out["conversation_id"]}).json()
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert client.delete("/api/assistant/history").status_code == 428
    assert client.delete("/api/assistant/history", params={"confirm": True}).json()["deleted"] == 2
    client.patch("/api/settings", json={"values": {"assistant": {"history_days": 0}}})
    say(client, "olá")
    assert client.get("/api/assistant/history").json() == []


# --------------------------------------------------------------------------- serviço de voz


def test_listening_off_keeps_microphone_closed(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    s = client.get("/api/voice/status").json()
    assert s["state"] == "off" and not s["mic"]["active"]
    assert s["external_audio"] is False and s["audio_stored"] is False
    assert FakeMic.instances == []
    say(client, "olá")  # texto funciona com a voz desligada
    assert FakeMic.instances == []


def test_wake_word_then_voice_command_creates_task(client: TestClient, voice, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    svc, stt, speaker = voice
    assert svc.detector is not None
    monkeypatch.setattr(svc.detector, "templates", [Template("user-1", "user", np.zeros((5, 13)))])
    monkeypatch.setattr(svc.detector, "detect", lambda pcm: True)
    s = client.put("/api/voice/listening", json={"enabled": True}).json()
    assert s["state"] == "wake" and s["mic"]["active"]
    mic = FakeMic.instances[-1]

    mic.feed(silence(300) + tone(600) + silence(900))  # «UAJI»
    wait_for(lambda: svc.state == "listening")
    assert speaker.spoken[0].startswith("Estou aqui")

    stt.next_text = "cria uma tarefa para testar a voz"
    mic.feed(tone(800) + silence(900))
    wait_for(lambda: client.get("/api/tasks").json()["total"] == 1)
    wait_for(lambda: any("Tarefa criada" in t for t in speaker.spoken))
    assert client.get("/api/tasks").json()["items"][0]["title"] == "Testar a voz"
    assert svc.last_transcript == "cria uma tarefa para testar a voz"
    # Depois da resposta, abre uma janela de seguimento e volta à espera da palavra.
    wait_for(lambda: svc.state in ("listening", "wake"))

    client.put("/api/voice/listening", json={"enabled": False})
    assert not mic.active and svc.state == "off"
    assert client.get("/api/settings").json()["voice"]["listening"] is False


def test_push_to_talk_uses_microphone_temporarily(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    svc, stt, speaker = voice
    client.patch("/api/settings", json={"values": {"voice": {"follow_up_seconds": 0}}})
    s = client.post("/api/voice/activate").json()
    assert s["state"] == "listening" and s["mic"]["temporary"]
    mic = FakeMic.instances[-1]
    stt.next_text = "quais são as minhas tarefas prioritárias"
    mic.feed(tone(700) + silence(900))
    wait_for(lambda: svc.state == "off")
    assert not mic.active  # fechado no fim do pedido
    assert speaker.spoken and "Próximos passos" in speaker.spoken[-1]


def test_errors_permission_stt_and_tts(client: TestClient, voice, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    svc, stt, speaker = voice
    monkeypatch.setattr(capture, "mic_permission", lambda: "denied")
    s = client.put("/api/voice/listening", json={"enabled": True}).json()
    assert s["state"] == "error" and "negado" in s["last_error"] and not s["listening_enabled"]
    assert FakeMic.instances == []

    monkeypatch.setattr(capture, "mic_permission", lambda: "authorized")
    stt.installed = False
    s = client.post("/api/voice/activate").json()
    assert s["state"] in ("error", "off") and "não está instalado" in s["last_error"]

    monkeypatch.setattr(tts, "available", lambda: False)
    before = len(speaker.spoken)
    out = client.post("/api/assistant/message", json={"text": "olá", "speak": True}).json()
    assert out["reply"] and len(speaker.spoken) == before  # resposta em texto, sem fala


def test_stop_and_resume_speech(client: TestClient, voice) -> None:  # type: ignore[no-untyped-def]
    svc, _, speaker = voice
    client.post("/api/assistant/message", json={"text": "faz o relatório do meu dia", "speak": True})
    assert speaker.spoken[-1].startswith("Relatório do dia")
    client.post("/api/voice/stop-speaking")
    assert speaker.stopped >= 1
    assert svc.status()["tts"]["can_resume"]


def test_real_speaker_can_be_interrupted_and_resumed(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    log = tmp_path / "said.txt"
    fake_say = tmp_path / "say"
    fake_say.write_text(f"#!/bin/sh\ncat >> {log}\necho >> {log}\nsleep 0.3\n")
    fake_say.chmod(fake_say.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(tts.shutil, "which", lambda name: str(fake_say))
    sp = tts.Speaker()
    sp.speak("Primeira frase. Segunda frase. Terceira frase.", "Joana")
    wait_for(lambda: log.exists() and "Primeira" in log.read_text())
    assert sp.stop() is True
    assert sp.can_resume
    sp.resume(block=True)
    said = log.read_text()
    assert "Segunda frase." in said and "Terceira frase." in said and "[[volm" in said


def test_voice_catalog_only_lists_installed_voices() -> None:
    voices = tts.list_voices("pt")
    if not tts.available():
        pytest.skip("macOS sem comando say")
    names = {v.name for v in voices}
    for v in voices:
        assert v.language.startswith("pt") and v.gender in ("female", "male", "unspecified")
    assert tts.resolve_voice("VozInexistente") is None
    assert names  # este Mac tem vozes pt instaladas
