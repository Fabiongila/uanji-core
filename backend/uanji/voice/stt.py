"""Reconhecimento de fala local com Vosk (modelo pequeno de português, ~50 MB).

Medido neste computador (MacBook Air 2015): carregamento ~4 s, transcrição ≈ tempo real,
~160 MB de memória. O áudio é processado em fluxo enquanto a pessoa fala, por isso a
transcrição fica pronta pouco depois do fim da frase. Nada é enviado para a Internet;
só o descarregamento inicial do modelo (pedido explicitamente pelo utilizador) a usa.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

MODEL_NAME = "vosk-model-small-pt-0.3"
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODEL_SIZE_MB = 31


class Recognizer(Protocol):
    def accept(self, pcm: bytes) -> str: ...  # devolve transcrição parcial
    def final(self) -> str: ...


class STTEngine(Protocol):
    name: str
    local: bool

    def status(self) -> dict[str, Any]: ...
    def ready(self) -> bool: ...
    def load(self) -> None: ...
    def recognizer(self) -> Recognizer: ...


def vosk_installed() -> bool:
    try:
        import vosk  # type: ignore[import-untyped]  # noqa: F401
    except Exception:
        return False
    return True


class _VoskRecognizer:
    """Agrupa o áudio em blocos de ~200 ms e só pede resultados parciais a cada ~0,6 s
    (pedir parciais a cada bloco de 30 ms torna o Vosk mais lento do que o tempo real nesta CPU)."""

    CHUNK_BYTES = 16000 * 2 // 5  # 200 ms
    PARTIAL_EVERY = 3  # blocos

    def __init__(self, model: Any) -> None:
        from vosk import KaldiRecognizer

        self._r = KaldiRecognizer(model, 16000)
        self._final_parts: list[str] = []
        self._buf = bytearray()
        self._chunks = 0
        self._partial = ""

    def _feed(self, pcm: bytes) -> None:
        if self._r.AcceptWaveform(pcm):
            text = json.loads(self._r.Result()).get("text", "")
            if text:
                self._final_parts.append(text)
            self._partial = ""
        elif self._chunks % self.PARTIAL_EVERY == 0:
            self._partial = json.loads(self._r.PartialResult()).get("partial", "")

    def accept(self, pcm: bytes) -> str:
        self._buf += pcm
        if len(self._buf) >= self.CHUNK_BYTES:
            chunk, self._buf = bytes(self._buf), bytearray()
            self._chunks += 1
            self._feed(chunk)
        return " ".join([*self._final_parts, self._partial]).strip()

    def final(self) -> str:
        if self._buf:
            self._r.AcceptWaveform(bytes(self._buf))
            self._buf = bytearray()
        text = json.loads(self._r.FinalResult()).get("text", "")
        return " ".join([*self._final_parts, text]).strip()


class VoskEngine:
    name = "vosk"
    local = True

    def __init__(self, models_dir: Path) -> None:
        self.models_dir = models_dir
        self._model: Any = None
        self._lock = threading.Lock()
        self.download_state: dict[str, Any] = {"active": False, "progress": 0.0, "error": ""}

    @property
    def model_path(self) -> Path:
        return self.models_dir / MODEL_NAME

    @staticmethod
    def _valid_model(path: Path) -> bool:
        # Os modelos Vosk usam «am/final.mdl» ou «final.mdl» na raiz (modelos pequenos).
        return (path / "am" / "final.mdl").exists() or (path / "final.mdl").exists()

    def model_installed(self) -> bool:
        return self._valid_model(self.model_path)

    def ready(self) -> bool:
        return vosk_installed() and self.model_installed()

    def status(self) -> dict[str, Any]:
        return {
            "engine": self.name,
            "local": True,
            "package_installed": vosk_installed(),
            "model": MODEL_NAME,
            "model_installed": self.model_installed(),
            "model_size_mb": MODEL_SIZE_MB,
            "loaded": self._model is not None,
            "download": self.download_state,
        }

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            if not self.ready():
                raise RuntimeError("Modelo de reconhecimento de fala não instalado.")
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            self._model = Model(str(self.model_path))

    def unload(self) -> None:
        with self._lock:
            self._model = None

    def recognizer(self) -> Recognizer:
        self.load()
        return _VoskRecognizer(self._model)

    # ------------------------------------------------------------------ instalação do modelo

    def download(self) -> None:
        """Descarrega e instala o modelo (só por pedido explícito do utilizador)."""
        import httpx

        if self.download_state["active"]:
            return
        self.download_state = {"active": True, "progress": 0.0, "error": ""}
        try:
            self.models_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.models_dir) as tmp:
                archive = Path(tmp) / "model.zip"
                with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=60.0) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length") or 0)
                    done = 0
                    with archive.open("wb") as f:
                        for chunk in r.iter_bytes(65536):
                            f.write(chunk)
                            done += len(chunk)
                            if total:
                                self.download_state["progress"] = round(done / total, 3)
                extract = Path(tmp) / "x"
                with zipfile.ZipFile(archive) as z:
                    root = extract.resolve()
                    for member in z.namelist():
                        # Protecção contra caminhos maliciosos no arquivo («zip slip»).
                        if not (extract / member).resolve().is_relative_to(root):
                            raise RuntimeError("Arquivo do modelo inválido.")
                    z.extractall(extract)  # noqa: S202 (caminhos verificados acima)
                src = extract / MODEL_NAME
                if not self._valid_model(src):
                    raise RuntimeError("O arquivo descarregado não contém o modelo esperado.")
                if self.model_path.exists():
                    shutil.rmtree(self.model_path)
                shutil.move(str(src), str(self.model_path))
            self.download_state = {"active": False, "progress": 1.0, "error": ""}
        except Exception as e:
            log.warning("Falha ao descarregar o modelo de voz: %s", e)
            msg = "Sem ligação à Internet." if "connect" in str(e).lower() else str(e)[:200]
            self.download_state = {"active": False, "progress": 0.0, "error": msg}
