"""Síntese de fala com as vozes instaladas no macOS (comando ``say``, totalmente local).

- O catálogo vem do próprio sistema (AVFoundation; alternativa: ``say -v ?``). Só são
  apresentadas vozes realmente instaladas.
- O género da voz é o declarado pelo sistema. As vozes «Eloquence» da Apple não o declaram;
  para essas usa-se a classificação publicada pela Apple para cada nome (marcada como tal).
- A leitura é feita frase a frase, para poder ser interrompida e retomada a partir da frase
  em que parou.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess  # noqa: S404 (comando fixo, sem shell)
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)

# Vozes «Eloquence» (macOS 13+): o sistema devolve género «não especificado».
CATALOG_GENDER = {
    "Eddy": "male",
    "Reed": "male",
    "Rocko": "male",
    "Grandpa": "male",
    "Flo": "female",
    "Sandy": "female",
    "Shelley": "female",
    "Grandma": "female",
}
SAMPLE_TEXT = "Olá. Sou o assistente do UANJI CORE. Esta é a minha voz."


@dataclass(frozen=True)
class Voice:
    id: str  # nome exacto aceite por «say -v» (ex.: «Eddy (Português (Brasil))»)
    name: str
    language: str
    gender: str  # female | male | unspecified
    gender_source: str  # system | catalog | none
    quality: str  # default | enhanced | premium

    def to_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


def _avfoundation_meta() -> dict[tuple[str, str], tuple[int, int]]:
    """(nome, idioma) → (género, qualidade) declarados pelo sistema."""
    try:
        import AVFoundation as av  # type: ignore[import-not-found,import-untyped,unused-ignore]
    except Exception:
        return {}
    return {
        (str(v.name()), str(v.language())): (int(v.gender()), int(v.quality()))
        for v in av.AVSpeechSynthesisVoice.speechVoices()
    }


def _say_voices() -> list[tuple[str, str, str]]:
    """(id para «say -v», nome, idioma) das vozes instaladas."""
    say = shutil.which("say")
    if not say:
        return []
    try:
        res = subprocess.run([say, "-v", "?"], capture_output=True, text=True, timeout=10, check=True)  # noqa: S603
    except (subprocess.SubprocessError, OSError):
        return []
    out = []
    for line in res.stdout.splitlines():
        m = re.match(r"^(?P<id>.+?)\s+(?P<lang>[a-z]{2,3}_[A-Za-z0-9]+)\s+#", line)
        if m:
            vid = m.group("id").strip()
            out.append((vid, re.sub(r"\s*\(.*\)$", "", vid), m.group("lang").replace("_", "-")))
    return out


@lru_cache(maxsize=1)
def _all_voices() -> tuple[Voice, ...]:
    meta = _avfoundation_meta()
    quality = {1: "default", 2: "enhanced", 3: "premium"}
    voices = []
    for vid, name, lang in _say_voices():
        g, q = meta.get((name, lang), (0, 1))
        if g in (1, 2):
            gender, src = ("male" if g == 1 else "female"), "system"
        elif name in CATALOG_GENDER:
            gender, src = CATALOG_GENDER[name], "catalog"
        else:
            gender, src = "unspecified", "none"
        voices.append(Voice(vid, name, lang, gender, src, quality.get(q, "default")))
    return tuple(voices)


def list_voices(language_prefix: str = "") -> list[Voice]:
    voices = [v for v in _all_voices() if v.language.lower().startswith(language_prefix.lower())]
    order = {"pt-AO": 0, "pt-PT": 1, "pt-BR": 2}
    return sorted(voices, key=lambda v: (order.get(v.language, 9), v.language, v.name))


def refresh_voices() -> None:
    _all_voices.cache_clear()


def available() -> bool:
    return shutil.which("say") is not None


def resolve_voice(voice_id: str) -> Voice | None:
    return next((v for v in _all_voices() if v.id == voice_id), None)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"[*_#`>|]+", " ", text)  # sem Markdown na leitura
    parts = re.split(r"(?<=[.!?;:])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


class Speaker:
    """Lê texto frase a frase. ``stop()`` interrompe; ``resume()`` continua da frase seguinte."""

    def __init__(self, on_state: Callable[[bool], None] | None = None) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sentences: list[str] = []
        self._index = 0
        self._opts: dict[str, Any] = {}
        self._interrupted = False
        self.on_state = on_state
        self.last_error = ""

    @property
    def speaking(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def can_resume(self) -> bool:
        """Há leitura interrompida: retoma a partir da frase em que foi interrompida."""
        return not self.speaking and self._interrupted and self._index < len(self._sentences)

    def speak(self, text: str, voice: str, rate: int = 185, volume: float = 0.9, block: bool = False) -> None:
        self.stop()
        self._sentences = split_sentences(text)
        self._index = 0
        self._opts = {"voice": voice, "rate": rate, "volume": volume}
        self._start(block)

    def resume(self, block: bool = False) -> bool:
        if not self.can_resume:
            return False
        self._start(block)
        return True

    def _start(self, block: bool) -> None:
        self._stop.clear()
        self._interrupted = False
        self._thread = threading.Thread(target=self._run, name="uanji-tts", daemon=True)
        self._thread.start()
        if block:
            self._thread.join()

    def _run(self) -> None:
        say = shutil.which("say")
        if not say:
            self.last_error = "Síntese de fala indisponível (comando «say» não encontrado)."
            return
        if self.on_state:
            self.on_state(True)
        try:
            volume = max(0.0, min(1.0, float(self._opts["volume"])))
            while self._index < len(self._sentences) and not self._stop.is_set():
                sentence = self._sentences[self._index]
                cmd = [say, "-r", str(int(self._opts["rate"]))]
                if self._opts["voice"]:
                    cmd += ["-v", str(self._opts["voice"])]
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._proc = subprocess.Popen(  # noqa: S603
                        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                    )
                # «[[volm x]]» é um comando embebido do sintetizador do macOS.
                _, err = self._proc.communicate(f"[[volm {volume:.2f}]] {sentence}".encode())
                if self._proc.returncode not in (0, -15) and not self._stop.is_set():
                    self.last_error = (err or b"").decode(errors="replace")[:200] or "Falha na síntese de fala."
                    log.warning("say falhou: %s", self.last_error)
                    break
                if not self._stop.is_set():
                    self._index += 1
        finally:
            with self._lock:
                self._proc = None
            if self.on_state:
                self.on_state(False)

    def stop(self) -> bool:
        """Interrompe a leitura. Devolve True se estava a falar."""
        was = self.speaking
        self._interrupted = was
        self._stop.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        return was
