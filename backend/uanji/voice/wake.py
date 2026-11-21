"""Detector local da palavra de activação por comparação de modelos (MFCC + DTW).

Técnica usada por detectores pessoais como o Raven (Rhasspy): o utilizador grava
algumas amostras da palavra («UAJI»); cada enunciado curto captado é comparado com
essas amostras. Não usa a Internet, não depende do vocabulário de um modelo de fala
(o «UAJI» não existe no léxico do Vosk) e é leve em CPU, porque só corre quando a
detecção de actividade de voz entrega um enunciado curto.

Sem amostras do utilizador, podem gerar-se amostras iniciais com as vozes do sistema
(`say`), menos fiáveis para a voz real; a interface recomenda gravar amostras próprias.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess  # noqa: S404 (comandos fixos, sem shell)
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .dsp import SAMPLE_RATE, Floats, dtw_distance, mfcc, pcm_to_float, rms

log = logging.getLogger(__name__)

MAX_WAKE_MS = 1800  # enunciados mais longos não são a palavra isolada
DEFAULT_THRESHOLD = 0.16
MIN_THRESHOLD, MAX_THRESHOLD = 0.06, 0.24


@dataclass
class Template:
    name: str
    source: str  # user | system
    features: Floats


def read_wav(path: Path) -> bytes:
    with wave.open(str(path)) as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError("WAV tem de ser mono, 16 bits, 16 kHz")
        return bytes(w.readframes(w.getnframes()))


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def trim_silence(pcm: bytes, rel: float = 0.15) -> bytes:
    """Remove silêncio inicial/final (limiar relativo ao pico de energia)."""
    x = pcm_to_float(pcm)
    if x.size == 0:
        return pcm
    hop = 160
    levels = np.array([rms(x[i : i + hop]) for i in range(0, x.size, hop)])
    if levels.max() <= 0:
        return pcm
    on = np.where(levels > levels.max() * rel)[0]
    if on.size == 0:
        return pcm
    a, b = max(0, (on[0] - 3) * hop), min(x.size, (on[-1] + 4) * hop)
    return pcm[a * 2 : b * 2]


def synthesize(word: str, voice: str) -> bytes | None:
    """Gera uma amostra com as vozes do sistema macOS (`say` + `afconvert`)."""
    say, afconvert = shutil.which("say"), shutil.which("afconvert")
    if not say or not afconvert:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = Path(tmp) / "w.aiff", Path(tmp) / "w.wav"
        try:
            subprocess.run([say, "-v", voice, "-o", str(aiff), word], check=True, timeout=20, capture_output=True)  # noqa: S603
            subprocess.run(  # noqa: S603
                [afconvert, "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(aiff), str(wav)],
                check=True,
                timeout=20,
                capture_output=True,
            )
            return trim_silence(read_wav(wav))
        except (subprocess.SubprocessError, OSError, ValueError):
            return None


class WakeDetector:
    def __init__(self, directory: Path, sensitivity: float = 1.0) -> None:
        self.directory = directory
        # >1 mais sensível (mais activações, incluindo falsas); <1 mais restritivo.
        self.sensitivity = sensitivity
        self.threshold = DEFAULT_THRESHOLD
        self.templates: list[Template] = []
        self.last_score: float | None = None

    # ------------------------------------------------------------------ amostras

    def load(self) -> None:
        self.templates = []
        if not self.directory.exists():
            return
        meta_path = self.directory / "templates.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        for wav in sorted(self.directory.glob("*.wav")):
            try:
                pcm = read_wav(wav)
            except (ValueError, wave.Error):
                continue
            self.templates.append(
                Template(wav.stem, meta.get(wav.stem, {}).get("source", "user"), mfcc(pcm_to_float(pcm)))
            )
        self.calibrate()

    def calibrate(self) -> None:
        """Limiar a partir da variação entre as amostras do utilizador (intra-locutor)."""
        user = [t for t in self.templates if t.source == "user"]
        if len(user) >= 2:
            d = [dtw_distance(a.features, b.features) for i, a in enumerate(user) for b in user[i + 1 :]]
            base = max(d) * 1.3
        else:
            base = DEFAULT_THRESHOLD
        self.threshold = float(min(MAX_THRESHOLD, max(MIN_THRESHOLD, base * self.sensitivity)))

    @property
    def mode(self) -> str:
        if any(t.source == "user" for t in self.templates):
            return "user"
        return "system" if self.templates else "none"

    def _save_meta(self, name: str, source: str) -> None:
        meta_path = self.directory / "templates.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta[name] = {"source": source}
        meta_path.write_text(json.dumps(meta, indent=2))

    def add(self, pcm: bytes, source: str = "user") -> str:
        pcm = trim_silence(pcm)
        ms = len(pcm) // 2 * 1000 // SAMPLE_RATE
        if ms < 200:
            raise ValueError("Amostra demasiado curta ou silenciosa. Fale mais perto do microfone.")
        if ms > MAX_WAKE_MS + 400:
            raise ValueError("Amostra demasiado longa: diga apenas a palavra de activação.")
        self.directory.mkdir(parents=True, exist_ok=True)
        idx = 1
        while (self.directory / f"{source}-{idx}.wav").exists():
            idx += 1
        name = f"{source}-{idx}"
        write_wav(self.directory / f"{name}.wav", pcm)
        self._save_meta(name, source)
        self.load()
        return name

    def remove(self, name: str) -> None:
        if not name.replace("-", "").isalnum():
            raise ValueError("Nome inválido")
        (self.directory / f"{name}.wav").unlink(missing_ok=True)
        self.load()

    def clear(self, source: str | None = None) -> None:
        for t in list(self.templates):
            if source is None or t.source == source:
                (self.directory / f"{t.name}.wav").unlink(missing_ok=True)
        self.load()

    def bootstrap_from_system(self, word: str, voices: list[str]) -> int:
        """Cria amostras iniciais com vozes do sistema (substitui as anteriores do sistema)."""
        self.clear("system")
        n = 0
        for v in voices:
            pcm = synthesize(word, v)
            if pcm:
                try:
                    self.add(pcm, "system")
                    n += 1
                except ValueError:
                    continue
        return n

    # ------------------------------------------------------------------ detecção

    def score(self, pcm: bytes) -> float | None:
        """Menor distância DTW a uma amostra (menor = mais parecido)."""
        if not self.templates:
            return None
        pcm = trim_silence(pcm)
        ms = len(pcm) // 2 * 1000 // SAMPLE_RATE
        if ms < 200 or ms > MAX_WAKE_MS:
            return None
        feats = mfcc(pcm_to_float(pcm))
        # Com amostras do utilizador, as do sistema são ignoradas (generalizam mal entre locutores).
        pool = [t for t in self.templates if t.source == "user"] or self.templates
        return min(dtw_distance(feats, t.features) for t in pool)

    def detect(self, pcm: bytes) -> bool:
        s = self.score(pcm)
        self.last_score = s
        return s is not None and s <= self.threshold
