"""Serviço de voz: coordena microfone, palavra de activação, STT, assistente e TTS.

Estados (reflectidos no núcleo visual da interface):
    off          escuta desligada; microfone fechado
    wake         à espera da palavra de activação (microfone aberto, processamento local)
    listening    a ouvir um pedido
    interpreting a transcrever e interpretar
    preparing    a consultar dados / preparar a resposta
    executing    a executar uma acção
    confirming   à espera de confirmação («sim» / «não» ou botões)
    speaking     a falar
    done         pedido concluído (transitório)
    error        erro (transitório; detalhe em ``last_error``)

Comportamento real:
- Com a aplicação aberta (mesmo minimizada) e a escuta activa, o microfone fica aberto e o
  áudio é analisado localmente, bloco a bloco; nada é gravado em disco nem enviado para fora.
- Com o Mac em repouso, o macOS suspende o áudio; a escuta retoma ao acordar.
- Com a aplicação fechada, o backend termina e nada é escutado.
- Enquanto o assistente fala, o áudio do microfone é ignorado (evita que se ouça a si próprio);
  para interromper usa-se o botão, a tecla Esc ou «UAJI, pára» depois de terminar.
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import runtime
from ..assistant.conversation import Assistant
from ..services.common import get_all_settings
from . import capture, tts
from .dsp import SAMPLE_RATE, Segmenter
from .stt import STTEngine, VoskEngine
from .wake import WakeDetector

log = logging.getLogger(__name__)

STATE_LABEL = {
    "off": "Escuta desligada",
    "wake": "À espera de «{word}»",
    "listening": "A ouvir",
    "interpreting": "A interpretar o pedido",
    "preparing": "A preparar a resposta",
    "executing": "A executar uma acção",
    "confirming": "A aguardar confirmação",
    "speaking": "A falar",
    "done": "Concluído",
    "error": "Erro",
}
SYSTEM_WAKE_VOICES = ["Joana", "Luciana", "Eddy (Português (Brasil))"]
LISTEN_TIMEOUT_S = 8.0


class Hub:
    """Difunde eventos para os clientes ligados por SSE (thread-safe)."""

    def __init__(self) -> None:
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = []
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subs = [(lp, s) for lp, s in self._subs if s is not q]

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, q in subs:

            def put(q: asyncio.Queue[dict[str, Any]] = q) -> None:
                if not q.full():
                    q.put_nowait(event)

            try:
                loop.call_soon_threadsafe(put)
            except RuntimeError:
                self.unsubscribe(q)


def _slug(word: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "uaji"


class VoiceService:
    def __init__(
        self,
        data_dir: Path,
        mic_factory: Callable[[], capture.AudioSource] = capture.Microphone,
        stt: STTEngine | None = None,
        speaker: tts.Speaker | None = None,
        assistant: Assistant | None = None,
    ) -> None:
        self.voice_dir = data_dir / "voice"
        self.hub = Hub()
        self._mic_factory = mic_factory
        self.mic: capture.AudioSource | None = None
        self.mic_temporary = False
        self.stt: STTEngine = stt or VoskEngine(self.voice_dir / "models")
        self.speaker = speaker or tts.Speaker()
        self.assistant = assistant or Assistant()
        self.segmenter = Segmenter()
        self.detector: WakeDetector | None = None
        self.settings: dict[str, Any] = {}
        self.state = "off"
        self.listening_enabled = False
        self.conversation_id: str | None = None
        self.last_error = ""
        self.partial = ""
        self.last_transcript = ""
        self._recognizer: Any = None
        self._listen_deadline = 0.0
        self._busy = threading.Lock()
        self._lock = threading.RLock()
        self._taps: list[Callable[[bytes], None]] = []
        self._bootstrapping = False
        self._last_partial_at = 0.0

    # ------------------------------------------------------------------ definições e estado

    @property
    def voice_cfg(self) -> dict[str, Any]:
        return dict(self.settings.get("voice") or {})

    def apply_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            old_word = self.voice_cfg.get("wake_word")
            self.settings = settings
            cfg = self.voice_cfg
            word = str(cfg.get("wake_word") or "UAJI")
            if self.detector is None or word != old_word:
                self.detector = WakeDetector(self.voice_dir / "wake" / _slug(word), float(cfg.get("sensitivity", 1.0)))
                self.detector.load()
            else:
                self.detector.sensitivity = float(cfg.get("sensitivity", 1.0))
                self.detector.calibrate()
            want = bool(cfg.get("listening"))
        if want and not self.listening_enabled:
            self.set_listening(True, persist=False)
        elif not want and self.listening_enabled:
            self.set_listening(False, persist=False)
        self._publish_status()

    def reload_settings(self) -> None:
        with runtime.get_database().session() as db:
            self.apply_settings(get_all_settings(db))

    def _set_state(self, state: str, error: str = "") -> None:
        self.state = state
        if error:
            self.last_error = error
        elif state not in ("error",):
            self.last_error = "" if state in ("listening", "wake") else self.last_error
        self._publish_status()

    def _publish_status(self) -> None:
        self.hub.publish({"type": "status", "status": self.status()})

    def status(self) -> dict[str, Any]:
        cfg = self.voice_cfg
        word = str(cfg.get("wake_word") or "UAJI")
        det = self.detector
        voice_name = str(cfg.get("voice") or "")
        return {
            "state": self.state,
            "label": STATE_LABEL.get(self.state, self.state).format(word=word),
            "listening_enabled": self.listening_enabled,
            "wake_word": word,
            "conversation_id": self.conversation_id,
            "mic": {
                "permission": capture.mic_permission(),
                "active": bool(self.mic and self.mic.active),
                "temporary": self.mic_temporary,
                "device": getattr(self.mic, "device", None) if self.mic else None,
            },
            "wake": {
                "mode": det.mode if det else "none",
                "samples": [{"name": t.name, "source": t.source} for t in det.templates] if det else [],
                "threshold": round(det.threshold, 3) if det else None,
                "last_score": round(det.last_score, 3) if det and det.last_score is not None else None,
                "preparing": self._bootstrapping,
            },
            "stt": self.stt.status(),
            "tts": {
                "available": tts.available(),
                "enabled": bool(cfg.get("tts_enabled", True)),
                "speaking": self.speaker.speaking,
                "can_resume": self.speaker.can_resume,
                "voice": voice_name,
                "voice_found": tts.resolve_voice(voice_name) is not None if voice_name else False,
                "last_error": self.speaker.last_error,
            },
            # Garantias de privacidade (verificadas pelos testes):
            "external_audio": False,
            "audio_stored": False,
            "last_error": self.last_error,
            "partial": self.partial,
            "last_transcript": self.last_transcript,
        }

    # ------------------------------------------------------------------ microfone

    def _open_mic(self, temporary: bool) -> None:
        if self.mic and self.mic.active:
            if not temporary:
                self.mic_temporary = False
            return
        perm = capture.mic_permission()
        if perm == "not_determined":
            perm = capture.request_mic_permission()
        if perm in ("denied", "restricted"):
            raise PermissionError(
                "O acesso ao microfone foi negado. Autorize em Definições do Sistema → Privacidade e Segurança → "
                "Microfone e reinicie a aplicação."
            )
        mic = self._mic_factory()
        try:
            mic.start(self._on_frame)
        except Exception as e:
            raise RuntimeError(f"Não foi possível abrir o microfone: {e}") from e
        self.mic = mic
        self.mic_temporary = temporary
        self.segmenter.reset()

    def _close_mic(self) -> None:
        if self.mic:
            self.mic.stop()
        self.mic = None
        self.mic_temporary = False
        self._recognizer = None

    def set_listening(self, enabled: bool, persist: bool = True) -> dict[str, Any]:
        """Liga/desliga a escuta contínua da palavra de activação."""
        with self._lock:
            if enabled:
                try:
                    self._open_mic(temporary=False)
                except (PermissionError, RuntimeError) as e:
                    self.listening_enabled = False
                    self._set_state("error", str(e))
                    if persist:
                        self._persist_listening(False)
                    return self.status()
                self.listening_enabled = True
                self._ensure_wake_templates()
                if self.state in ("off", "error", "done"):
                    self._set_state("wake")
            else:
                self.listening_enabled = False
                if self.state in ("wake", "listening", "off", "error", "done"):
                    self._close_mic()
                    self._set_state("off")
                elif self.mic and self.mic.active:
                    self.mic_temporary = True  # fecha no fim do pedido em curso
        if persist:
            self._persist_listening(enabled)
        self._publish_status()
        return self.status()

    def _persist_listening(self, enabled: bool) -> None:
        from ..services.common import put_setting

        with runtime.get_database().session() as db:
            cfg = get_all_settings(db)["voice"]
            put_setting(db, "voice", {**cfg, "listening": enabled})
        self.settings.setdefault("voice", {})["listening"] = enabled

    def _ensure_wake_templates(self) -> None:
        """Sem amostras, gera amostras iniciais com vozes do sistema (em segundo plano)."""
        det = self.detector
        if det is None or det.templates or self._bootstrapping:
            return

        def work() -> None:
            self._bootstrapping = True
            self._publish_status()
            try:
                det.bootstrap_from_system(str(self.voice_cfg.get("wake_word") or "UAJI"), SYSTEM_WAKE_VOICES)
            finally:
                self._bootstrapping = False
                self._publish_status()

        threading.Thread(target=work, name="uanji-wake-bootstrap", daemon=True).start()

    # ------------------------------------------------------------------ fluxo de áudio

    def _on_frame(self, pcm: bytes) -> None:
        for tap in list(self._taps):
            tap(pcm)
        state = self.state
        if self.speaker.speaking or state not in ("wake", "listening", "confirming"):
            if state not in ("wake", "listening", "confirming"):
                self.segmenter.reset()
            return
        if state in ("listening", "confirming"):
            self._feed_recognizer(pcm)
            if not self.segmenter.in_speech and time.monotonic() > self._listen_deadline:
                self._end_listening()
                return
        for utterance in self.segmenter.feed(pcm):
            if self.state == "wake":
                self._check_wake(utterance)
            elif self.state in ("listening", "confirming"):
                self._finish_utterance()

    def _check_wake(self, utterance: bytes) -> None:
        det = self.detector
        if det is None or not det.templates:
            return
        hit = det.detect(utterance)
        self.hub.publish({"type": "wake_score", "score": det.last_score, "threshold": det.threshold, "hit": hit})
        if hit:
            threading.Thread(target=self._on_wake, name="uanji-wake", daemon=True).start()

    def _on_wake(self) -> None:
        self.hub.publish({"type": "wake"})
        self._set_state("speaking")
        self._say(_greeting(self.settings))
        self._start_listening()

    def _start_listening(self, timeout: float = LISTEN_TIMEOUT_S) -> None:
        try:
            self._recognizer = self.stt.recognizer() if self.stt.ready() else None
        except Exception as e:
            log.exception("Falha ao carregar o STT")
            self._recognizer = None
            self._set_state("error", f"Reconhecimento de fala indisponível: {e}")
            self._settle(keep_error=True)
            return
        if self._recognizer is None:
            self._set_state(
                "error",
                "O modelo de reconhecimento de fala não está instalado. Instale-o em Definições → Voz e "
                "personalidade, ou escreva o pedido.",
            )
            self._settle(keep_error=True)
            return
        self.partial = ""
        self.segmenter.reset()
        self._listen_deadline = time.monotonic() + timeout
        self._set_state("listening")

    def _feed_recognizer(self, pcm: bytes) -> None:
        if self._recognizer is None:
            return
        try:
            partial = self._recognizer.accept(pcm)
        except Exception:
            log.exception("Erro do reconhecimento de fala")
            return
        now = time.monotonic()
        if partial and partial != self.partial and now - self._last_partial_at > 0.25:
            self.partial = partial
            self._last_partial_at = now
            self.hub.publish({"type": "partial", "text": partial})

    def _finish_utterance(self) -> None:
        rec, self._recognizer = self._recognizer, None
        if rec is None:
            return
        self._set_state("interpreting")
        threading.Thread(target=self._process_voice, args=(rec,), name="uanji-turn", daemon=True).start()

    def _end_listening(self) -> None:
        """Tempo de escuta esgotado sem fala."""
        self._recognizer = None
        self.partial = ""
        self._after_turn(awaiting=None)

    def _process_voice(self, rec: Any) -> None:
        try:
            text = rec.final().strip()
        except Exception as e:
            log.exception("Erro na transcrição")
            self._set_state("error", f"Erro no reconhecimento de fala: {e}")
            self._after_turn(awaiting=None)
            return
        self.partial = ""
        if not text:
            self._set_state("error", "Não percebi o que disse. Tente de novo, mais perto do microfone.")
            self._after_turn(awaiting=None)
            return
        self.last_transcript = text
        self.hub.publish({"type": "transcript", "text": text})
        self._run_turn(text, "voice", speak=True)

    # ------------------------------------------------------------------ pedidos (voz e texto)

    def _phase(self, phase: str) -> None:
        self._set_state(phase)

    def _run_turn(self, text: str, source: str, speak: bool) -> dict[str, Any]:
        with self._busy:
            self._set_state("interpreting")
            turn = self.assistant.handle(text, self.conversation_id, source=source, on_phase=self._phase)
            self.conversation_id = turn["conversation_id"]
            self.hub.publish({"type": "turn", "turn": turn, "source": source, "text": text})
            control = turn.get("control")
            if control == "cancel":
                self.speaker.stop()
            if turn["error"]:
                self._set_state("error", turn["reply"])
            elif turn["awaiting"] == "confirmation":
                self._set_state("confirming")
            else:
                self._set_state("done")
            if control == "resume":
                if self.speaker.resume(block=source == "voice"):
                    self._set_state("speaking")
            elif speak and control != "cancel":
                self._say(turn["speech"], block=source == "voice")
        if source == "voice":
            self._after_turn(turn.get("awaiting"))
        elif not self.speaker.speaking:
            self._settle()
        return turn

    def text_turn(self, text: str, conversation_id: str | None = None, speak: bool = False) -> dict[str, Any]:
        if conversation_id:
            self.conversation_id = conversation_id
        speak = speak and bool(self.voice_cfg.get("tts_enabled", True))
        return self._run_turn(text, "text", speak)

    def _after_turn(self, awaiting: str | None) -> None:
        """Depois de responder por voz: janela de seguimento ou regresso à espera."""
        follow = float(self.voice_cfg.get("follow_up_seconds", 8) or 0)
        if self.mic and self.mic.active and (awaiting or follow > 0):
            self._start_listening(timeout=max(follow, LISTEN_TIMEOUT_S if awaiting else follow))
            if self.state == "listening" and awaiting == "confirmation":
                self._set_state("confirming")
            return
        self._settle()

    def _settle(self, keep_error: bool = False) -> None:
        error = self.last_error if keep_error else ""
        if self.mic_temporary or not self.listening_enabled:
            self._close_mic()
            self._set_state("off")
        else:
            self._set_state("wake")
        if error:
            self.last_error = error
            self._publish_status()

    def _say(self, text: str, block: bool = True) -> None:
        cfg = self.voice_cfg
        if not cfg.get("tts_enabled", True) or not text.strip():
            return
        if not tts.available():
            self.last_error = "Síntese de fala indisponível neste sistema; a resposta fica só em texto."
            return
        prev = self.state

        def on_state(speaking: bool) -> None:
            if speaking:
                self._set_state("speaking")
            elif not block and self.state == "speaking":
                self._settle()

        self.speaker.on_state = on_state
        self.speaker.speak(
            text,
            str(cfg.get("voice") or ""),
            int(cfg.get("rate", 185)),
            float(cfg.get("volume", 0.9)),
            block=block,
        )
        if block and self.state == "speaking":
            self.state = prev
        if self.speaker.last_error:
            self.last_error = self.speaker.last_error

    # ------------------------------------------------------------------ comandos da interface

    def activate(self) -> dict[str, Any]:
        """Botão do microfone: ouve um pedido agora, sem palavra de activação."""
        with self._lock:
            if self.state in ("listening", "confirming"):
                return self.status()
            self.speaker.stop()
            try:
                self._open_mic(temporary=not self.listening_enabled)
            except (PermissionError, RuntimeError) as e:
                self._set_state("error", str(e))
                return self.status()
        self._start_listening()
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self.speaker.stop()
        self._recognizer = None
        self.partial = ""
        self._settle()
        return self.status()

    def stop_speaking(self) -> dict[str, Any]:
        self.speaker.stop()
        if self.state == "speaking":
            self._settle()
        return self.status()

    def resume_speaking(self) -> dict[str, Any]:
        self.speaker.on_state = lambda s: self._set_state("speaking") if s else self._settle()
        self.speaker.resume()
        return self.status()

    def speak_text(
        self, text: str, voice: str | None = None, rate: int | None = None, volume: float | None = None
    ) -> None:
        cfg = self.voice_cfg
        self.speaker.on_state = lambda s: self._set_state("speaking") if s else self._settle()
        self.speaker.speak(
            text,
            voice if voice is not None else str(cfg.get("voice") or ""),
            rate or int(cfg.get("rate", 185)),
            volume if volume is not None else float(cfg.get("volume", 0.9)),
        )

    def record(self, seconds: float = 2.5) -> bytes:
        """Grava áudio curto (amostras da palavra de activação). Usa o microfone aberto ou abre-o."""
        frames: list[bytes] = []
        done = threading.Event()
        needed = int(seconds * SAMPLE_RATE * 2)

        def tap(pcm: bytes) -> None:
            frames.append(pcm)
            if sum(map(len, frames)) >= needed:
                done.set()

        opened = False
        with self._lock:
            if not (self.mic and self.mic.active):
                self._open_mic(temporary=True)
                opened = True
            self._taps.append(tap)
        try:
            if not done.wait(seconds + 3):
                raise RuntimeError("O microfone não entregou áudio. Verifique o dispositivo de entrada.")
        finally:
            self._taps.remove(tap)
            if opened:
                self._close_mic()
        return b"".join(frames)[:needed]

    # ------------------------------------------------------------------ iniciativa do assistente

    def proactive(self, nudge: Any) -> bool:
        """Entrega uma mensagem por iniciativa do assistente. ``False`` se estiver ocupado."""
        if self.state not in ("off", "wake", "done", "error") or self.speaker.speaking:
            return False
        if not self._busy.acquire(blocking=False):
            return False
        try:
            if not self.conversation_id:
                self.conversation_id = str(uuid.uuid4())
            cid = self.conversation_id
            self.assistant.remember(cid, nudge.text, {"proactive": nudge.rule, "offer": nudge.to_dict()["offer"]})
            if nudge.offer:
                self.assistant.offer(cid, nudge.offer[0], nudge.offer[1])
            turn = {
                "id": str(uuid.uuid4()),
                "conversation_id": cid,
                "reply": nudge.text,
                "speech": nudge.text,
                "engine": "local",
                "report": None,
                "actions": [],
                "executed": [],
                "consulted": [],
                "navigate": None,
                "awaiting": "offer" if nudge.offer else None,
                "control": None,
                "error": False,
                "proactive": nudge.rule,
                "offer": nudge.to_dict()["offer"],
                "link": nudge.link,
            }
            self.hub.publish({"type": "proactive", "turn": turn})
        finally:
            self._busy.release()
        from ..activity import monitor as activity

        live = activity.get().state if activity.get().enabled else None
        in_meeting = live is not None and live.category == "reunioes"
        pcfg = self.settings.get("proactive") or {}
        if pcfg.get("voice", True) and self.voice_cfg.get("tts_enabled", True) and not in_meeting:
            threading.Thread(
                target=self._speak_proactive, args=(nudge,), name="uanji-proactive-say", daemon=True
            ).start()
        return True

    def _speak_proactive(self, nudge: Any) -> None:
        self._say(nudge.text, block=True)
        if nudge.offer and self.mic and self.mic.active and self.stt.ready():
            # Como numa conversa: depois da pergunta, ouve a resposta sem precisar de «UAJI».
            self._start_listening(timeout=10)
        elif self.state == "speaking":
            self._settle()

    def shutdown(self) -> None:
        self.speaker.stop()
        self._close_mic()


def _greeting(settings: dict[str, Any]) -> str:
    from ..assistant.persona import Persona

    return Persona.from_settings(settings).greeting(str((settings.get("voice") or {}).get("greeting") or ""))


_service: VoiceService | None = None
_service_lock = threading.Lock()


def get() -> VoiceService:
    global _service
    with _service_lock:
        if _service is None:
            _service = VoiceService(runtime.get_settings().data_dir)
            _service.reload_settings()
        return _service


def set_service(service: VoiceService | None) -> None:
    """Substitui o serviço (testes) ou limpa-o (encerramento)."""
    global _service
    with _service_lock:
        if _service is not None and service is not _service:
            _service.shutdown()
        _service = service
