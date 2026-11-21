"""Fornecedor «modelo próprio»: qualquer servidor compatível com a API OpenAI Chat Completions.

Serve para usar um modelo seu, local ou remoto, sem alterar o resto da aplicação:
- Ollama (``http://localhost:11434/v1``), LM Studio (``http://localhost:1234/v1``),
  llama.cpp ``server`` (``http://localhost:8080/v1``), vLLM, LocalAI;
- serviços remotos compatíveis (OpenRouter, Groq, Together, Azure OpenAI, OpenAI…).

O modelo usa as mesmas ferramentas internas que o fornecedor Anthropic (via «function
calling»). Se o modelo não suportar ferramentas, responde só com texto e as acções ficam
disponíveis apenas pelos comandos locais.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from ..errors import ExternalServiceError, ValidationFailed
from .core import ProviderTurn


def check_base_url(url: str) -> str:
    u = url.strip().rstrip("/")
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise ValidationFailed("Endereço inválido. Exemplo: http://localhost:11434/v1")
    if p.scheme == "http" and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValidationFailed("Servidores remotos têm de usar https (http só para localhost).")
    return u


def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]},
        }
        for t in tools
    ]


def _messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte o histórico interno (formato das ferramentas) para mensagens OpenAI."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if m["role"] == "assistant" and isinstance(content, dict) and content.get("_openai"):
            out.append(content["message"])
        elif m["role"] == "user" and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": str(block["content"])})
        else:
            out.append({"role": m["role"], "content": content if isinstance(content, str) else json.dumps(content)})
    return out


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model:
            raise ValidationFailed("Indique o nome do modelo (ex.: llama3.1, qwen2.5:7b).")
        self.base_url = check_base_url(base_url)
        self.model = model
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self.client.post("/chat/completions", json=payload)
        except httpx.ConnectError as e:
            raise ExternalServiceError(f"Sem ligação ao modelo em {self.base_url}. O servidor está a correr?") from e
        except httpx.TimeoutException as e:
            raise ExternalServiceError("O modelo demorou demasiado a responder.") from e
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"Erro de ligação ao modelo: {type(e).__name__}") from e
        if r.status_code == 401:
            raise ExternalServiceError("Chave do servidor do modelo inválida (401).")
        if r.status_code == 404:
            raise ExternalServiceError(f"Modelo «{self.model}» ou endereço não encontrado (404).")
        if r.status_code >= 400:
            raise ExternalServiceError(f"O servidor do modelo respondeu {r.status_code}: {r.text[:200]}")
        data: dict[str, Any] = r.json()
        return data

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderTurn:
        payload: dict[str, Any] = {"model": self.model, "messages": _messages(system, messages), "temperature": 0.3}
        if tools:
            payload["tools"] = _tools(tools)
        try:
            data = self._post(payload)
        except ExternalServiceError as e:
            # Modelos sem suporte a ferramentas: tenta só com texto.
            if tools and ("tool" in e.message.lower() or "400" in e.message):
                payload.pop("tools", None)
                data = self._post(payload)
            else:
                raise
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append({"id": c.get("id") or fn.get("name", "call"), "name": fn.get("name", ""), "input": args})
        stop = "tool_use" if calls else "end_turn"
        raw = {
            "_openai": True,
            "message": {
                "role": "assistant",
                "content": msg.get("content") or "",
                **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {}),
            },
        }
        return ProviderTurn(text=msg.get("content") or "", tool_calls=calls, stop_reason=stop, raw_content=raw)

    def list_models(self) -> list[str]:
        try:
            r = self.client.get("/models", timeout=10.0)
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"Sem ligação a {self.base_url}.") from e
        if r.status_code >= 400:
            raise ExternalServiceError(f"O servidor respondeu {r.status_code} ao listar modelos.")
        return [str(m.get("id")) for m in (r.json().get("data") or []) if m.get("id")]
