"""Processamento de sinal leve (NumPy): MFCC, DTW e detecção de actividade de voz (VAD).

Tudo corre localmente. Áudio: PCM 16 bits, mono, 16 kHz.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

SAMPLE_RATE = 16_000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480

Floats = npt.NDArray[np.float64]


def pcm_to_float(pcm: bytes) -> Floats:
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float64) / 32768.0


def rms(x: Floats) -> float:
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


# --------------------------------------------------------------------------- MFCC


def _mel(f: Floats | float) -> Floats | float:
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_inv(m: Floats) -> Floats:
    return 700.0 * (10 ** (m / 2595.0) - 1.0)


def _filterbank(n_filters: int, n_fft: int, sr: int) -> Floats:
    mels = np.linspace(_mel(0.0), _mel(sr / 2), n_filters + 2)
    bins = np.floor((n_fft + 1) * _mel_inv(np.asarray(mels)) / sr).astype(int)
    fb = np.zeros((n_filters, n_fft // 2 + 1))
    for i in range(1, n_filters + 1):
        lo, mid, hi = bins[i - 1], bins[i], bins[i + 1]
        for k in range(lo, mid):
            fb[i - 1, k] = (k - lo) / max(mid - lo, 1)
        for k in range(mid, hi):
            fb[i - 1, k] = (hi - k) / max(hi - mid, 1)
    return fb


_N_FFT = 512
_FB = _filterbank(26, _N_FFT, SAMPLE_RATE)
_N_MFCC = 13
_DCT = np.cos(np.pi / 26 * (np.arange(26) + 0.5)[None, :] * np.arange(_N_MFCC)[:, None])


def mfcc(signal: Floats, win: int = 400, hop: int = 160) -> Floats:
    """MFCC (13 coeficientes) com normalização por média/variância (robusto ao volume)."""
    if signal.size < win:
        signal = np.pad(signal, (0, win - signal.size))
    emph = np.append(signal[0], signal[1:] - 0.97 * signal[:-1])
    n = 1 + (emph.size - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = emph[idx] * np.hamming(win)
    power = np.abs(np.fft.rfft(frames, _N_FFT)) ** 2 / _N_FFT
    energies = np.log(np.maximum(power @ _FB.T, 1e-10))
    feats = energies @ _DCT.T
    feats -= feats.mean(axis=0)
    std = feats.std(axis=0)
    return np.asarray(feats / np.where(std < 1e-6, 1.0, std))


def dtw_distance(a: Floats, b: Floats, band: float = 0.35) -> float:
    """DTW com distância de cosseno, normalizada pelo comprimento (0 = idêntico).

    Banda de Sakoe-Chiba para limitar o custo; ignora c0 (energia) para ser robusto ao volume.
    """
    a, b = a[:, 1:], b[:, 1:]
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return float("inf")
    an = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)
    bn = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-9)
    cost = 1.0 - an @ bn.T
    w = max(int(band * max(n, m)), abs(n - m) + 1)
    acc = np.full((n + 1, m + 1), np.inf)
    acc[0, 0] = 0.0
    for i in range(1, n + 1):
        lo, hi = max(1, i - w), min(m, i + w)
        prev = acc[i - 1]
        row = acc[i]
        for j in range(lo, hi + 1):
            row[j] = cost[i - 1, j - 1] + min(prev[j], row[j - 1], prev[j - 1])
    return float(acc[n, m] / (n + m))


# --------------------------------------------------------------------------- VAD


@dataclass
class Segmenter:
    """Segmenta áudio contínuo em enunciados por energia, com limiar de ruído adaptativo.

    Custo muito baixo: só calcula a energia de cada bloco de 30 ms. Os enunciados são
    entregues apenas quando terminam (silêncio > ``hangover_ms``) ou excedem ``max_ms``.
    """

    min_ms: int = 250
    max_ms: int = 12_000
    hangover_ms: int = 700
    ratio: float = 3.0
    min_level: float = 0.006
    noise: float = 0.004
    _buf: list[bytes] = field(default_factory=list)
    _pre: list[bytes] = field(default_factory=list)
    _voiced: bool = False
    _silence_ms: int = 0
    _ms: int = 0

    @property
    def threshold(self) -> float:
        return max(self.noise * self.ratio, self.min_level)

    @property
    def in_speech(self) -> bool:
        return self._voiced

    def reset(self) -> None:
        self._buf, self._pre = [], []
        self._voiced, self._silence_ms, self._ms = False, 0, 0

    def feed(self, pcm: bytes) -> Iterator[bytes]:
        for start in range(0, len(pcm) - 1, FRAME_SAMPLES * 2):
            frame = pcm[start : start + FRAME_SAMPLES * 2]
            level = rms(pcm_to_float(frame))
            loud = level > self.threshold
            if not self._voiced:
                # Actualiza o ruído de fundo apenas em silêncio.
                self.noise = 0.95 * self.noise + 0.05 * min(level, 0.05)
                self._pre = (self._pre + [frame])[-10:]  # 300 ms antes do início
                if loud:
                    self._voiced = True
                    self._buf = list(self._pre)
                    self._ms = len(self._buf) * FRAME_MS
                    self._silence_ms = 0
                continue
            self._buf.append(frame)
            self._ms += FRAME_MS
            self._silence_ms = 0 if loud else self._silence_ms + FRAME_MS
            if self._silence_ms >= self.hangover_ms or self._ms >= self.max_ms:
                speech_ms = self._ms - self._silence_ms
                out = b"".join(self._buf)
                self.reset()
                if speech_ms >= self.min_ms:
                    yield out
