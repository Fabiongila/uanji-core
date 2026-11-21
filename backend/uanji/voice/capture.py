"""Captura de áudio do microfone (PortAudio via ``sounddevice``) e permissões do macOS.

O microfone só é aberto quando a escuta está activa ou durante um pedido explícito
(botão do microfone, gravação de amostra). Fechado, não consome CPU nem é usado.

Permissão: o macOS atribui o acesso ao microfone à aplicação responsável pelo processo
(na app instalada, o UANJI CORE; em desenvolvimento, o Terminal). O pedido mostra a
mensagem definida em ``NSMicrophoneUsageDescription``.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np

from .dsp import FRAME_SAMPLES, SAMPLE_RATE

log = logging.getLogger(__name__)

PERMISSION_LABEL = {
    "authorized": "Autorizado",
    "denied": "Negado",
    "restricted": "Restrito pelo sistema",
    "not_determined": "Ainda não pedido",
    "unknown": "Desconhecido",
}


def mic_permission() -> str:
    try:
        import AVFoundation as av  # type: ignore[import-not-found,import-untyped,unused-ignore]

        status = int(av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeAudio))
    except Exception:
        return "unknown"
    return {0: "not_determined", 1: "restricted", 2: "denied", 3: "authorized"}.get(status, "unknown")


def request_mic_permission(timeout: float = 60.0) -> str:
    """Mostra o pedido do sistema (só aparece quando o estado é «não determinado»)."""
    try:
        import AVFoundation as av  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except Exception:
        return "unknown"
    done = threading.Event()
    av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(av.AVMediaTypeAudio, lambda granted: done.set())
    done.wait(timeout)
    return mic_permission()


def input_device() -> dict[str, Any] | None:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        info = sd.query_devices(kind="input")
    except Exception:
        return None
    return {"name": info["name"], "default_samplerate": info["default_samplerate"]}


class AudioSource(Protocol):
    active: bool

    def start(self, on_frame: Callable[[bytes], None]) -> None: ...
    def stop(self) -> None: ...


def _resample(x: np.ndarray, src_rate: float) -> np.ndarray:
    if int(src_rate) == SAMPLE_RATE:
        return x
    n = int(len(x) * SAMPLE_RATE / src_rate)
    out: np.ndarray = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.int16)
    return out


class Microphone:
    """Entrega blocos PCM 16 bits mono 16 kHz de 30 ms a ``on_frame`` (numa thread própria)."""

    def __init__(self) -> None:
        self.active = False
        self._stream: Any = None
        self._q: queue.Queue[bytes | None] = queue.Queue(maxsize=200)
        self._worker: threading.Thread | None = None
        self.device: dict[str, Any] | None = None

    def start(self, on_frame: Callable[[bytes], None]) -> None:
        if self.active:
            return
        import sounddevice as sd

        dev = sd.query_devices(kind="input")
        rate = float(dev["default_samplerate"])
        try:
            # Preferir 16 kHz directamente (o CoreAudio converte); senão, converte-se aqui.
            sd.check_input_settings(samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            rate = float(SAMPLE_RATE)
        except Exception:
            log.info("16 kHz não suportado directamente; a converter de %s Hz", rate)
        block = int(rate * FRAME_SAMPLES / SAMPLE_RATE)

        def callback(indata: Any, frames: int, t: Any, status: Any) -> None:
            data = np.frombuffer(bytes(indata), dtype=np.int16)
            # Processamento atrasado: descarta em vez de acumular memória.
            with contextlib.suppress(queue.Full):
                self._q.put_nowait(_resample(data, rate).tobytes())

        self._q = queue.Queue(maxsize=200)
        self._stream = sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", blocksize=block, callback=callback)
        self._stream.start()
        self.device = {"name": dev["name"], "samplerate": rate}
        self.active = True

        def pump() -> None:
            while True:
                item = self._q.get()
                if item is None:
                    return
                try:
                    on_frame(item)
                except Exception:
                    log.exception("Erro no processamento de áudio")

        self._worker = threading.Thread(target=pump, name="uanji-audio", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        if not self.active:
            return
        self.active = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            log.exception("Erro ao fechar o microfone")
        self._stream = None
        self._q.put(None)
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
