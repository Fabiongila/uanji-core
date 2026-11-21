"""Auto-teste do pipeline de voz com componentes reais, sem microfone.

Gera com as vozes do sistema «UAJI» seguido de um pedido, injecta esse áudio no serviço de
voz (como se viesse do microfone) e verifica: detecção da palavra de activação, transcrição
local (Vosk), execução real no assistente (base de dados temporária) e síntese de fala.

    cd backend && .venv/bin/python -m uanji.voice.selftest [--models DIR] [--voice NOME]

Não substitui o teste com o microfone real (ver docs/VOICE.md), mas mede o pipeline nesta máquina.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from .dsp import FRAME_SAMPLES
from .wake import synthesize


class InjectedMic:
    """Fonte de áudio que reproduz PCM pré-gerado em tempo real (blocos de 30 ms)."""

    def __init__(self) -> None:
        self.active = False
        self.device = {"name": "Áudio sintetizado (auto-teste)", "samplerate": 16000}
        self.cb: Callable[[bytes], None] | None = None

    def start(self, on_frame: Callable[[bytes], None]) -> None:
        self.active, self.cb = True, on_frame

    def stop(self) -> None:
        self.active = False

    def play(self, pcm: bytes, realtime: bool = True) -> None:
        step = FRAME_SAMPLES * 2
        for i in range(0, len(pcm), step):
            if self.active and self.cb:
                self.cb(pcm[i : i + step])
            if realtime:
                time.sleep(0.03)


def main() -> int:  # noqa: C901
    ap = argparse.ArgumentParser()
    default_models = Path(__file__).resolve().parents[3] / ".dev-data" / "voice" / "models"
    ap.add_argument("--models", type=Path, default=default_models)
    ap.add_argument("--wake-voice", default="Reed (Português (Brasil))", help="voz que diz «UAJI» (≠ das amostras)")
    ap.add_argument("--voice", default="Joana", help="voz que diz o pedido")
    args = ap.parse_args()

    from fastapi.testclient import TestClient

    from ..config import Settings
    from ..main import create_app
    from ..services.vault import MemoryStore
    from . import capture, service

    tmp = Path(tempfile.mkdtemp(prefix="uanji-selftest-"))
    ok = True
    try:
        (tmp / "voice").mkdir(parents=True)
        if not (args.models / "vosk-model-small-pt-0.3").exists():
            print(f"✗ Modelo Vosk não encontrado em {args.models}")
            return 2
        (tmp / "voice" / "models").symlink_to(args.models.resolve())
        settings = Settings(
            env="test",
            data_dir=tmp,
            token="t",
            secret_backend="memory",
            scheduler_enabled=False,
        )
        app = create_app(settings, secret_store=MemoryStore())
        mic = InjectedMic()
        capture.mic_permission = lambda: "authorized"
        svc = service.VoiceService(tmp, mic_factory=lambda: mic)
        svc.reload_settings()
        service.set_service(svc)
        client = TestClient(app, headers={"Authorization": "Bearer t"})
        client.patch("/api/settings", json={"values": {"voice": {"volume": 0.0, "follow_up_seconds": 0}}})

        t = time.time()
        assert svc.detector is not None
        n = svc.detector.bootstrap_from_system("UAJI", service.SYSTEM_WAKE_VOICES)
        print(f"• Amostras do sistema para «UAJI»: {n} ({time.time() - t:.1f} s)")
        wake = synthesize("Uaji", args.wake_voice)
        request = synthesize("Cria uma tarefa para testar a voz", args.voice)
        if not wake or not request:
            print("✗ Não foi possível sintetizar áudio (comando say).")
            return 2
        silence = b"\x00\x00" * 16000

        client.put("/api/voice/listening", json={"enabled": True})
        print(f"• Estado inicial: {svc.state}; limiar {svc.detector.threshold:.3f}")
        t = time.time()
        mic.play(silence[:9600] + wake + silence)
        deadline = time.time() + 30
        while svc.state not in ("listening",) and time.time() < deadline:
            time.sleep(0.05)
        score = svc.detector.last_score
        if svc.state != "listening":
            print(f"✗ Palavra de activação não detectada (distância {score}, limiar {svc.detector.threshold:.3f})")
            return 1
        print(f"✓ «UAJI» detectado (distância {score:.3f}) e saudação falada em {time.time() - t:.1f} s")

        t = time.time()
        mic.play(request + silence)
        deadline = time.time() + 60
        while client.get("/api/tasks").json()["total"] == 0 and time.time() < deadline:
            time.sleep(0.1)
        tasks = client.get("/api/tasks").json()["items"]
        print(f"• Transcrição: «{svc.last_transcript}»")
        if tasks:
            print(f"✓ Tarefa criada por voz: «{tasks[0]['title']}» ({time.time() - t:.1f} s desde o início do pedido)")
        else:
            print("✗ Nenhuma tarefa criada.")
            ok = False
        client.put("/api/voice/listening", json={"enabled": False})
        deadline = time.time() + 30
        while mic.active and time.time() < deadline:  # fecha no fim da resposta em curso
            time.sleep(0.1)
        print(f"{'✓' if not mic.active else '✗'} Escuta desligada; microfone fechado: {not mic.active}")
        ok = ok and not mic.active
        service.set_service(None)
        app.state.database.dispose()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
