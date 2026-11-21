"""Rotas de voz: estado, escuta, activação manual, vozes, amostras da palavra de activação,
modelo de reconhecimento e fluxo de eventos (SSE)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..errors import NotFound, ServiceUnavailable, ValidationFailed
from ..voice import capture, tts
from ..voice import service as voice_service
from ..voice.wake import trim_silence

router = APIRouter(tags=["voice"])


class ListeningIn(BaseModel):
    enabled: bool


class VoiceTestIn(BaseModel):
    voice: str = Field(default="", max_length=100)
    rate: int = Field(default=185, ge=90, le=360)
    volume: float = Field(default=0.9, ge=0.0, le=1.0)
    text: str = Field(default="", max_length=500)


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


@router.get("/voice/status")
def status() -> dict[str, Any]:
    return voice_service.get().status()


@router.put("/voice/listening")
def set_listening(body: ListeningIn) -> dict[str, Any]:
    return voice_service.get().set_listening(body.enabled)


@router.post("/voice/activate")
def activate() -> dict[str, Any]:
    """Ouve um pedido agora (botão do microfone), sem palavra de activação."""
    return voice_service.get().activate()


@router.post("/voice/cancel")
def cancel() -> dict[str, Any]:
    return voice_service.get().cancel()


@router.post("/voice/stop-speaking")
def stop_speaking() -> dict[str, Any]:
    return voice_service.get().stop_speaking()


@router.post("/voice/resume-speaking")
def resume_speaking() -> dict[str, Any]:
    return voice_service.get().resume_speaking()


@router.post("/voice/speak")
def speak(body: SpeakIn) -> dict[str, Any]:
    """Lê um texto (ex.: relatório aberto na interface) com a voz configurada."""
    if not tts.available():
        raise ServiceUnavailable("Síntese de fala indisponível neste sistema.")
    voice_service.get().speak_text(body.text)
    return voice_service.get().status()


@router.get("/voice/voices")
def voices(all_languages: bool = False) -> dict[str, Any]:
    items = [v.to_dict() for v in tts.list_voices("" if all_languages else "pt")]
    has_ao = any(v["language"] == "pt-AO" for v in items)
    return {
        "available": tts.available(),
        "voices": items,
        "notes": []
        if has_ao
        else [
            "O macOS não inclui vozes de português de Angola. As vozes disponíveis são de português europeu "
            "(pt-PT) e do Brasil (pt-BR).",
            "Pode instalar mais vozes em Definições do Sistema → Acessibilidade → Conteúdo falado → Voz do "
            "sistema → Gerir vozes. Aparecem aqui automaticamente depois de reiniciar a aplicação.",
        ],
    }


@router.post("/voice/test")
def test_voice(body: VoiceTestIn) -> dict[str, bool]:
    if not tts.available():
        raise ServiceUnavailable("Síntese de fala indisponível neste sistema.")
    if body.voice and tts.resolve_voice(body.voice) is None:
        raise NotFound(f"A voz «{body.voice}» não está instalada.")
    voice_service.get().speak_text(body.text or tts.SAMPLE_TEXT, body.voice, body.rate, body.volume)
    return {"ok": True}


@router.post("/voice/permission")
def request_permission() -> dict[str, str]:
    """Mostra o pedido de acesso ao microfone do macOS (se ainda não foi decidido)."""
    return {"permission": capture.request_mic_permission()}


# --------------------------------------------------------------------------- Palavra de activação


@router.get("/voice/wake")
def wake_samples() -> dict[str, Any]:
    wake: dict[str, Any] = voice_service.get().status()["wake"]
    return wake


@router.post("/voice/wake/record")
def record_wake_sample() -> dict[str, Any]:
    """Grava 2,5 s; o utilizador diz a palavra de activação uma vez."""
    svc = voice_service.get()
    try:
        pcm = svc.record(2.5)
    except (PermissionError, RuntimeError) as e:
        raise ServiceUnavailable(str(e)) from e
    assert svc.detector is not None
    try:
        name = svc.detector.add(pcm, "user")
    except ValueError as e:
        raise ValidationFailed(str(e)) from e
    svc._publish_status()
    return {"name": name, **svc.status()["wake"]}


@router.post("/voice/wake/test")
def test_wake() -> dict[str, Any]:
    """Grava 2,5 s e indica se seria reconhecido como palavra de activação (não guarda nada)."""
    svc = voice_service.get()
    try:
        pcm = svc.record(2.5)
    except (PermissionError, RuntimeError) as e:
        raise ServiceUnavailable(str(e)) from e
    det = svc.detector
    assert det is not None
    if not det.templates:
        raise ValidationFailed("Ainda não há amostras da palavra de activação.")
    hit = det.detect(trim_silence(pcm))
    return {"detected": hit, "score": det.last_score, "threshold": det.threshold}


@router.delete("/voice/wake/{name}")
def delete_wake_sample(name: str) -> dict[str, Any]:
    svc = voice_service.get()
    assert svc.detector is not None
    try:
        svc.detector.remove(name)
    except ValueError as e:
        raise ValidationFailed(str(e)) from e
    svc._publish_status()
    wake: dict[str, Any] = svc.status()["wake"]
    return wake


@router.post("/voice/wake/system")
def bootstrap_system_samples() -> dict[str, Any]:
    """Gera amostras com vozes do sistema (útil antes de gravar as próprias)."""
    svc = voice_service.get()
    assert svc.detector is not None
    n = svc.detector.bootstrap_from_system(svc.status()["wake_word"], voice_service.SYSTEM_WAKE_VOICES)
    svc._publish_status()
    return {"created": n, **svc.status()["wake"]}


# --------------------------------------------------------------------------- Modelo de STT


@router.post("/voice/model/download")
def download_model() -> dict[str, Any]:
    """Descarrega o modelo local de reconhecimento de fala (~31 MB, requer Internet uma vez)."""
    svc = voice_service.get()
    engine = svc.stt
    download = getattr(engine, "download", None)
    if download is None:
        raise ValidationFailed("Este motor de reconhecimento não precisa de descarregar modelos.")

    def work() -> None:
        download()
        svc._publish_status()

    threading.Thread(target=work, daemon=True).start()
    return engine.status()


# --------------------------------------------------------------------------- Eventos (SSE)


@router.get("/voice/events")
async def events(request: Request) -> StreamingResponse:
    """Eventos em tempo real: estado, transcrição parcial, respostas. Pedido com cabeçalho Authorization."""
    svc = voice_service.get()
    q = svc.hub.subscribe()

    async def stream() -> AsyncIterator[str]:
        try:
            yield f"data: {json.dumps({'type': 'status', 'status': svc.status()}, default=str)}\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
        finally:
            with contextlib.suppress(Exception):
                svc.hub.unsubscribe(q)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
