"""Execução de ferramentas e acções pendentes de confirmação.

Cada execução corre numa sessão própria: se o serviço falhar, a transacção é revertida
e o assistente informa o erro. O sucesso só é anunciado depois do *commit*.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from .. import runtime
from ..errors import AppError, NotFound, ValidationFailed
from ..services.common import log_activity
from .tools import TOOLS_BY_NAME, Tool, ToolResult

log = logging.getLogger(__name__)

PENDING_TTL_SECONDS = 30 * 60
ActionStatus = Literal["pending", "confirmed", "rejected", "failed", "expired"]


@dataclass
class PendingAction:
    id: str
    tool: str
    params: dict[str, Any]
    summary: str
    risk: str
    details: list[str] = field(default_factory=list)
    origin: str = "local"
    conversation_id: str | None = None
    status: ActionStatus = "pending"
    result: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    created: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "summary": self.summary,
            "risk": self.risk,
            "details": self.details,
            "params": self.params,
            "status": self.status,
            "message": self.message,
            "result": self.result,
        }


_pending: dict[str, PendingAction] = {}
_lock = threading.Lock()


def _expire() -> None:
    now = time.monotonic()
    for a in list(_pending.values()):
        if a.status == "pending" and now - a.created > PENDING_TTL_SECONDS:
            a.status = "expired"
        if now - a.created > PENDING_TTL_SECONDS * 4:
            _pending.pop(a.id, None)


def execute(tool: Tool, params: BaseModel, origin: str = "local") -> ToolResult:
    """Executa a ferramenta numa transacção própria (commit antes de devolver)."""
    with runtime.get_database().session() as db:
        result = tool.run(db, params)
        if tool.risk != "read":
            entity = result.entity or {"type": "assistant", "id": tool.name}
            log_activity(
                db,
                entity["type"] if entity["type"] in ("project", "task", "note", "checklist") else "assistant",
                entity["id"],
                "assistant_action",
                f"Assistente ({'IA' if origin == 'ai' else 'comando local'}): {result.message[:300]}",
            )
    return result


def propose(tool: Tool, params: BaseModel, origin: str, conversation_id: str | None = None) -> PendingAction:
    """Regista uma acção à espera de confirmação, com a descrição do que vai mudar."""
    with runtime.get_database().session() as db:
        details = tool.describe(db, params) if tool.describe else []
        summary = tool.summary(db, params) or tool.name
    a = PendingAction(
        id=str(uuid.uuid4()),
        tool=tool.name,
        params=params.model_dump(),
        summary=summary,
        risk=tool.risk,
        details=[d for d in details if d],
        origin=origin,
        conversation_id=conversation_id,
    )
    with _lock:
        _expire()
        _pending[a.id] = a
    return a


def get(action_id: str) -> PendingAction | None:
    with _lock:
        _expire()
        return _pending.get(action_id)


def pending_for(conversation_id: str) -> PendingAction | None:
    with _lock:
        _expire()
        found = [a for a in _pending.values() if a.conversation_id == conversation_id and a.status == "pending"]
    return found[-1] if found else None


def decide(action_id: str, approve: bool) -> tuple[PendingAction, ToolResult | None]:
    """Confirma ou rejeita. Erros do serviço ficam registados na acção (estado «failed»)."""
    with _lock:
        _expire()
        a = _pending.get(action_id)
        if a is None:
            raise NotFound("Acção proposta não encontrada (pode ter expirado ou a aplicação foi reiniciada).")
        if a.status != "pending":
            raise ValidationFailed(
                "Esta acção expirou. Peça-a novamente." if a.status == "expired" else "Esta acção já foi tratada."
            )
        a.status = "confirmed" if approve else "rejected"  # reservada antes de executar (evita duplicação)
    if not approve:
        a.message = "Acção cancelada. Nada foi alterado."
        return a, None
    tool = TOOLS_BY_NAME[a.tool]
    try:
        result = execute(tool, tool.params.model_validate(a.params), a.origin)
    except AppError as e:
        a.status = "failed"
        a.message = f"Não foi possível concluir: {e.message}"
        return a, None
    except Exception:
        log.exception("Falha ao executar a acção %s", a.tool)
        a.status = "failed"
        a.message = "Não foi possível concluir a acção devido a um erro interno. Nada foi confirmado."
        return a, None
    a.result = result.data if isinstance(result.data, dict) else {"data": result.data}
    a.message = result.message
    return a, result
