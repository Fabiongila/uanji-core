"""Gestão da conversa: interpreta, executa ferramentas e produz a resposta (texto + fala).

Ordem de decisão em cada pedido:
1. Resposta a algo que o assistente perguntou (parâmetro em falta, escolha, confirmação).
2. Comandos de controlo (repete, cancela, sim/não, ajuda).
3. Interpretação local (``intents``) → ferramenta interna.
4. Fornecedor de IA, se configurado; caso contrário, explica o que entende.

O texto e a voz passam exactamente pelo mesmo caminho.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select

from .. import runtime
from ..errors import AppError
from ..models import AssistantMessage, utcnow
from ..services.common import get_all_settings
from . import actions, core
from .intents import Intent, Parser, normalize, squash
from .persona import Persona
from .tools import RISK_LABEL, TOOLS_BY_NAME, Ambiguous, needs_confirmation

log = logging.getLogger(__name__)

HELP_EXAMPLES = [
    "Quais são as minhas tarefas prioritárias de hoje?",
    "Cria uma tarefa para rever a autenticação do Q360.",
    "Regista uma ideia: …",
    "Faz o relatório do meu dia.",
    "Qual dos meus projectos está mais atrasado?",
    "Mostra-me as automações que falharam.",
    "Abre o projecto Gestão Escolar.",
]
ORDINALS = {
    "primeiro": 0,
    "primeira": 0,
    "1": 0,
    "um": 0,
    "segundo": 1,
    "segunda": 1,
    "2": 1,
    "dois": 1,
    "terceiro": 2,
    "terceira": 2,
    "3": 2,
    "tres": 2,
    "quarto": 3,
    "quarta": 3,
    "4": 3,
    "quinto": 4,
    "5": 4,
}


@dataclass
class Awaiting:
    kind: str  # slot | choice
    tool: str
    params: dict[str, Any]
    param: str
    options: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Context:
    id: str
    last_project: dict[str, str] | None = None
    awaiting: Awaiting | None = None
    last_turn: dict[str, Any] | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    # Oferta feita por iniciativa do assistente («Quer o relatório?»): «sim» executa-a.
    offer: dict[str, Any] | None = None


_contexts: dict[str, Context] = {}
_lock = threading.Lock()
MAX_CONTEXTS = 20


def _context(conversation_id: str | None) -> Context:
    with _lock:
        cid = conversation_id or str(uuid.uuid4())
        ctx = _contexts.get(cid)
        if ctx is None:
            if len(_contexts) >= MAX_CONTEXTS:
                _contexts.pop(next(iter(_contexts)))
            ctx = Context(cid)
            _contexts[cid] = ctx
        return ctx


def reset_contexts() -> None:
    with _lock:
        _contexts.clear()


@dataclass
class Turn:
    conversation_id: str
    reply: str
    speech: str = ""
    engine: str = "local"
    report: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    executed: list[dict[str, Any]] = field(default_factory=list)
    consulted: list[dict[str, Any]] = field(default_factory=list)
    navigate: str | None = None
    awaiting: str | None = None  # confirmation | slot | choice
    control: str | None = None  # repeat | cancel | resume (tratados também pelo serviço de voz)
    error: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "reply": self.reply,
            "speech": self.speech or self.reply,
            "engine": self.engine,
            "report": self.report,
            "actions": self.actions,
            "executed": self.executed,
            "consulted": self.consulted,
            "navigate": self.navigate,
            "awaiting": self.awaiting,
            "control": self.control,
            "error": self.error,
        }


class Assistant:
    """Ponto único de entrada do assistente (texto e voz)."""

    def __init__(self, provider: core.Provider | None = None) -> None:
        self.provider = provider  # apenas testes; normalmente vem das Definições
        self._phase: Callable[[str], None] = lambda _p: None

    # ------------------------------------------------------------------ API pública

    def handle(
        self,
        text: str,
        conversation_id: str | None = None,
        source: str = "text",
        on_phase: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """``on_phase`` recebe «preparing» (consulta/IA) ou «executing» (escrita) para o núcleo visual."""
        self._phase = on_phase or (lambda _p: None)
        ctx = _context(conversation_id)
        settings = self._settings()
        persona = Persona.from_settings(settings)
        text = text.strip()[:4000]
        self._store(ctx.id, "user", text, source, {})
        try:
            turn = self._dispatch(ctx, text, persona, settings)
        except Exception:
            log.exception("Falha ao processar o pedido do assistente")
            turn = Turn(ctx.id, "Ocorreu um erro interno ao processar o pedido. Nada foi alterado.", error=True)
        if turn.control != "repeat":
            ctx.last_turn = turn.to_dict()
        ctx.history += [{"role": "user", "content": text}, {"role": "assistant", "content": turn.reply}]
        turns = int(settings["assistant"].get("context_turns", 12))
        ctx.history = ctx.history[-2 * max(1, turns) :]
        self._store(
            ctx.id,
            "assistant",
            turn.reply,
            source,
            {
                k: v
                for k, v in turn.to_dict().items()
                if k in ("engine", "report", "actions", "executed", "navigate", "error")
            },
        )
        return turn.to_dict()

    def offer(self, conversation_id: str, tool: str, params: dict[str, Any]) -> None:
        """Regista uma oferta: a próxima resposta «sim»/«não» nesta conversa decide-a."""
        ctx = _context(conversation_id)
        ctx.offer = {"tool": tool, "params": params}
        ctx.awaiting = None

    def remember(self, conversation_id: str, text: str, meta: dict[str, Any]) -> None:
        """Guarda uma mensagem por iniciativa do assistente no contexto e no histórico."""
        ctx = _context(conversation_id)
        ctx.history = [*ctx.history, {"role": "assistant", "content": text}][-24:]
        self._store(ctx.id, "assistant", text, "proactive", meta)

    def decide(self, action_id: str, approve: bool) -> dict[str, Any]:
        a, result = actions.decide(action_id, approve)
        cid = a.conversation_id or str(uuid.uuid4())
        turn = Turn(cid, a.message, actions=[a.to_dict()], error=a.status == "failed")
        if result is not None:
            turn.executed.append({"tool": a.tool, "message": result.message, "entity": result.entity})
            turn.navigate = result.navigate
            self._remember_entity(_context(cid), result.entity)
        self._store(cid, "assistant", turn.reply, "text", {"actions": turn.actions})
        return turn.to_dict()

    # ------------------------------------------------------------------ decisão

    @staticmethod
    def _settings() -> dict[str, Any]:
        with runtime.get_database().session() as db:
            return get_all_settings(db)

    def _parser(self, settings: dict[str, Any]) -> Parser:
        return Parser([str(settings["voice"].get("wake_word") or "UAJI")])

    def _dispatch(self, ctx: Context, text: str, persona: Persona, settings: dict[str, Any]) -> Turn:
        parser = self._parser(settings)
        intent = parser.parse(text)

        # 1. Confirmação pendente nesta conversa.
        pending = actions.pending_for(ctx.id)
        if pending and intent.kind == "control" and intent.control in ("confirm", "reject"):
            return self._decide_turn(ctx, pending.id, intent.control == "confirm")

        # Uma oferta só vale para a resposta imediatamente a seguir.
        if not (intent.kind == "control" and intent.control in ("confirm", "reject", "repeat")):
            ctx.offer = None

        # 2. Resposta a uma pergunta do assistente.
        if ctx.awaiting and not (intent.kind == "control" and intent.control in ("cancel", "repeat", "help")):
            aw = ctx.awaiting
            ctx.awaiting = None
            if aw.kind == "choice":
                chosen = self._choose(aw.options, parser.strip_prefixes(text))
                if chosen is None:
                    return Turn(ctx.id, "Não percebi qual escolheu. Pode repetir o pedido completo.")
                return self._run(ctx, aw.tool, {**aw.params, aw.param: chosen["id"]}, persona, settings)
            value = re.sub(r"^\s*(?:e |é |a ideia e |a tarefa e )", "", parser.strip_prefixes(text), flags=re.I)
            value = value.strip(" .")
            if not value:
                return Turn(ctx.id, "Não recebi nada. O pedido foi cancelado.")
            params = {**aw.params, aw.param: value[:1].upper() + value[1:]}
            if aw.tool == "create_note":
                params["title"] = params["title"][:300]
                params.setdefault("content", value)
            return self._run(ctx, aw.tool, params, persona, settings)

        # 3. Controlo.
        if intent.kind == "control":
            return self._control(ctx, intent, persona, settings)

        # 4. Ferramenta local.
        if intent.kind == "tool" and intent.tool:
            params = dict(intent.params)
            if intent.needs_project_context:
                if ctx.last_project is None:
                    ctx.awaiting = Awaiting("slot", intent.tool, params, "project")
                    return Turn(ctx.id, "De que projecto está a falar?", awaiting="slot")
                params["project"] = ctx.last_project["id"]
            if intent.missing:
                ctx.awaiting = Awaiting("slot", intent.tool, params, intent.missing)
                return Turn(ctx.id, intent.prompt or "Pode dar mais detalhes?", awaiting="slot")
            if intent.tool == "create_checklist" and self._ai_configured(settings):
                return self._ai(ctx, text, settings)
            turn = self._run(ctx, intent.tool, params, persona, settings)
            if params.get("kind") == "weekly" and "revis" in normalize(text) and not turn.error:
                turn.navigate = "/planning"  # «prepara a revisão semanal» abre também o planeamento
            return turn

        # 5. IA ou ajuda.
        if self._ai_configured(settings):
            return self._ai(ctx, text, settings)
        return Turn(
            ctx.id,
            "Não percebi o pedido. Sem um fornecedor de IA configurado, entendo pedidos como: "
            + "; ".join(f"«{e}»" for e in HELP_EXAMPLES[:4])
            + ".",
            engine="none",
        )

    def _decide_turn(self, ctx: Context, action_id: str, approve: bool) -> Turn:
        self._phase("executing" if approve else "preparing")
        d = self.decide(action_id, approve)
        t = Turn(
            ctx.id, d["reply"], actions=d["actions"], executed=d["executed"], navigate=d["navigate"], error=d["error"]
        )
        t.id = d["id"]
        return t

    def _control(self, ctx: Context, intent: Intent, persona: Persona, settings: dict[str, Any]) -> Turn:
        c = intent.control
        if c in ("confirm", "reject") and ctx.offer:
            offer, ctx.offer = ctx.offer, None
            if c == "reject":
                return Turn(ctx.id, "Está bem.")
            return self._run(ctx, offer["tool"], offer["params"], persona, settings)
        if c in ("confirm", "reject"):
            return Turn(ctx.id, "Não há nenhuma acção à espera de confirmação.")
        if c == "cancel":
            ctx.awaiting = None
            pending = actions.pending_for(ctx.id)
            if pending:
                actions.decide(pending.id, False)
            return Turn(ctx.id, "Cancelado.", control="cancel")
        if c == "repeat":
            if not ctx.last_turn:
                return Turn(ctx.id, "Ainda não tenho nenhuma resposta para repetir.", control="repeat")
            last = ctx.last_turn
            return Turn(ctx.id, last["reply"], speech=last["speech"], report=last["report"], control="repeat")
        if c == "resume":
            return Turn(ctx.id, "A retomar a leitura.", control="resume")
        if c == "help":
            return Turn(
                ctx.id,
                "Posso consultar e alterar os seus dados. Experimente, por exemplo: "
                + "; ".join(f"«{e}»" for e in HELP_EXAMPLES)
                + ".",
            )
        if c == "thanks":
            return Turn(ctx.id, "De nada.")
        return Turn(ctx.id, persona.greeting(str(settings["voice"].get("greeting") or "")))

    @staticmethod
    def _choose(options: list[dict[str, str]], answer: str) -> dict[str, str] | None:
        a = squash(normalize(answer))
        for word in a.split():
            if word in ORDINALS and ORDINALS[word] < len(options):
                return options[ORDINALS[word]]
        for o in options:
            label = squash(normalize(o["label"]))
            if a and (a in label or label in a):
                return o
        return None

    @staticmethod
    def _ai_configured(settings: dict[str, Any]) -> bool:
        return core.is_configured(settings["assistant"])

    # ------------------------------------------------------------------ execução

    def _remember_entity(self, ctx: Context, entity: dict[str, str] | None) -> None:
        if entity and entity.get("type") == "project":
            ctx.last_project = entity

    def _run(self, ctx: Context, name: str, params: dict[str, Any], persona: Persona, settings: dict[str, Any]) -> Turn:
        tool = TOOLS_BY_NAME[name]
        try:
            p = tool.params.model_validate(params)
        except ValidationError as e:
            first = e.errors()[0]
            return Turn(
                ctx.id, f"Pedido incompleto ou inválido ({first.get('loc', [''])[0]}: {first['msg']}).", error=True
            )
        try:
            with runtime.get_database().session() as db:
                confirm = needs_confirmation(db, tool, "local")
            if confirm:
                a = actions.propose(tool, p, "local", ctx.id)
                detail = f" {'; '.join(a.details[:3])}." if a.details else ""
                risk = " Atenção: esta operação é irreversível." if tool.risk == "destructive" else ""
                return Turn(
                    ctx.id,
                    f"Preciso da sua confirmação para: {a.summary}.{detail}{risk} Confirma?",
                    speech=f"Preciso da sua confirmação para: {a.summary}.{risk} Diga sim para confirmar ou não "
                    "para cancelar.",
                    actions=[a.to_dict()],
                    awaiting="confirmation",
                )
            self._phase("preparing" if tool.risk == "read" else "executing")
            result = actions.execute(tool, p, "local")
        except Ambiguous as e:
            ctx.awaiting = Awaiting("choice", name, params, _ref_param(tool.params), e.options)
            listing = "; ".join(f"{i + 1}. {o['label']}" for i, o in enumerate(e.options))
            return Turn(ctx.id, f"{e.message} Qual deles? {listing}.", awaiting="choice")
        except AppError as e:
            return Turn(ctx.id, e.message, error=True)
        if result.delegate is not None:
            return self._run(ctx, result.delegate[0], result.delegate[1], persona, settings)
        self._remember_entity(ctx, result.entity)
        turn = Turn(ctx.id, result.message, navigate=result.navigate)
        if tool.risk == "read":
            turn.consulted.append({"tool": name, "input": p.model_dump()})
        else:
            turn.executed.append(
                {"tool": name, "message": result.message, "entity": result.entity, "risk": RISK_LABEL[tool.risk]}
            )
        if result.report is not None:
            turn.report = result.report.to_dict()
            turn.reply = result.report.speech
            turn.speech = persona.report_intro(result.report.title) + " " + result.report.speech.split(". ", 1)[-1]
        return turn

    def _ai(self, ctx: Context, text: str, settings: dict[str, Any]) -> Turn:
        self._phase("preparing")
        note = (
            f"projecto em foco: {ctx.last_project['label']} (id {ctx.last_project['id']})" if ctx.last_project else ""
        )
        try:
            with runtime.get_database().session() as db:
                if settings["activity"].get("enabled"):
                    from ..activity import insights

                    # Personalização: o que a pessoa tem feito hoje no computador (resumo, sem títulos).
                    today = insights.summary_sentence(insights.summarize(db))
                    note = f"{note}; actividade de hoje: {today}" if note else f"actividade de hoje: {today}"
                out = core.chat(
                    db, ctx.history, text, provider=self.provider, conversation_id=ctx.id, context_note=note
                )
        except AppError as e:
            return Turn(ctx.id, f"O fornecedor de IA não respondeu: {e.message}", engine="ai", error=True)
        turn = Turn(
            ctx.id,
            out["reply"] or "(O fornecedor não devolveu texto.)",
            engine="ai",
            consulted=out["consulted"],
            actions=out["proposed_actions"],
            navigate=out.get("navigate"),
            awaiting="confirmation" if out["proposed_actions"] else None,
        )
        return turn

    # ------------------------------------------------------------------ histórico

    @staticmethod
    def _store(cid: str, role: str, content: str, source: str, meta: dict[str, Any]) -> None:
        try:
            with runtime.get_database().session() as db:
                if int(get_all_settings(db)["assistant"].get("history_days", 30)) <= 0:
                    return
                db.add(
                    AssistantMessage(conversation_id=cid, role=role, source=source, content=content[:20000], meta=meta)
                )
        except Exception:
            log.exception("Não foi possível guardar o histórico do assistente")


def _ref_param(model: type[Any]) -> str:
    for name in ("project", "task", "automation", "template"):
        if name in model.model_fields:
            return name
    return str(next(iter(model.model_fields)))


def history(conversation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    with runtime.get_database().session() as db:
        stmt = select(AssistantMessage).order_by(AssistantMessage.created_at.desc()).limit(limit)
        if conversation_id:
            stmt = stmt.where(AssistantMessage.conversation_id == conversation_id)
        rows = list(db.scalars(stmt))
        return [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "role": m.role,
                "source": m.source,
                "content": m.content,
                "meta": m.meta,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(rows)
        ]


def purge_history(days: int | None = None) -> int:
    """Remove mensagens mais antigas do que a retenção configurada (``None`` = usar Definições; 0 = tudo)."""
    with runtime.get_database().session() as db:
        keep = int(get_all_settings(db)["assistant"].get("history_days", 30)) if days is None else days
        stmt = delete(AssistantMessage)
        if keep > 0:
            stmt = stmt.where(AssistantMessage.created_at < utcnow() - timedelta(days=keep))
        result = db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
