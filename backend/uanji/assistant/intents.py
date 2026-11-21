"""Interpretação local (sem IA e sem Internet) de pedidos em português.

Reconhece os pedidos frequentes e converte-os em chamadas às ferramentas internas.
O que não reconhece é passado ao fornecedor de IA, se estiver configurado; caso
contrário o assistente diz que não percebeu e sugere exemplos — nunca adivinha
uma acção de escrita.

As expressões regulares correm sobre uma versão normalizada do texto (minúsculas,
sem acentos nem pontuação) com o mesmo comprimento do original, para que os
títulos sejam extraídos do texto original, com acentos e maiúsculas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

Control = Literal["repeat", "cancel", "confirm", "reject", "help", "greet", "thanks", "resume", "none"]


@dataclass
class Intent:
    kind: Literal["tool", "control", "unknown"]
    tool: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    control: Control = "none"
    # Parâmetro em falta que o assistente deve pedir (ex.: o texto da ideia).
    missing: str | None = None
    prompt: str | None = None
    # O pedido refere «este projecto» e depende do contexto da conversa.
    needs_project_context: bool = False


def _fold(ch: str) -> str:
    if ch.isalnum():
        base = unicodedata.normalize("NFD", ch)[0].lower()
        return base if len(base) == 1 else ch
    return ch if ch in "/+-" else " "


def normalize(text: str) -> str:
    """Mesmo comprimento que ``text``: cada carácter é mapeado para um único carácter."""
    return "".join(_fold(c) for c in text)


def squash(s: str) -> str:
    return " ".join(s.split())


def _clean_slot(s: str) -> str:
    s = squash(s).strip(" .,:;!?«»\"'")
    return s[:1].upper() + s[1:] if s else s


PRIORITY_WORDS = {
    "urgente": "critical",
    "critica": "critical",
    "prioridade critica": "critical",
    "prioridade alta": "high",
    "alta prioridade": "high",
    "importante": "high",
    "prioridade baixa": "low",
    "baixa prioridade": "low",
}
STATUS_WORDS = {
    "em curso": "in_progress",
    "em progresso": "in_progress",
    "em andamento": "in_progress",
    "bloqueada": "blocked",
    "bloqueado": "blocked",
    "por fazer": "todo",
    "pendente": "todo",
    "concluida": "done",
    "concluido": "done",
    "feita": "done",
}
DUE_RE = re.compile(
    r"\s+(?:para|ate|com prazo(?: para| ate)?)\s+(?:a\s+|o\s+)?"
    r"(?P<due>hoje|amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo|\d{1,2}/\d{1,2}(?:/\d{4})?)"
    r"(?:\s+feira)?\s*$"
)
PROJECT_SUFFIX_RE = re.compile(r"\s+(?:no|do|para o|ao)\s+projec?to\s+(?P<project>.+?)\s*$")

THIS_PROJECT = r"(?:este|esse|deste|desse|neste|nesse|do|o)\s+projec?to"


class Parser:
    def __init__(self, wake_words: list[str] | None = None) -> None:
        words = [normalize(w).strip() for w in (wake_words or []) if w.strip()]
        words += ["uaji", "uanji", "wanji", "waji", "uaje"]
        alts = "|".join(sorted({re.escape(w) for w in words}, key=len, reverse=True))
        self._wake = re.compile(rf"^\s*(?:(?:ola|ei|hey|ok)\s+)?(?:{alts})\b\s*")
        self._polite = re.compile(r"^\s*(?:por favor|podes|pode|consegues|consegue|quero que|preciso que)\s+")

    # ------------------------------------------------------------------ utilitários

    def strip_prefixes(self, text: str) -> str:
        """Remove a palavra de activação e fórmulas de cortesia iniciais."""
        for _ in range(3):
            n = normalize(text)
            m = self._wake.match(n) or self._polite.match(n)
            if not m:
                break
            text = text[m.end() :]
        n = normalize(text)
        m = re.search(r"\s+por favor\s*$", n)
        if m:
            text = text[: m.start()]
        return text.strip()

    @staticmethod
    def _extract_modifiers(original: str) -> tuple[str, dict[str, Any]]:
        """Separa prazo, prioridade e projecto do fim do título."""
        params: dict[str, Any] = {}
        text = original.rstrip(" .!?")
        for _ in range(3):
            n = normalize(text)
            m = DUE_RE.search(n)
            if m:
                params["due"] = m.group("due")
                text = text[: m.start()]
                continue
            m = PROJECT_SUFFIX_RE.search(n)
            if m:
                params["project"] = _clean_slot(text[m.start("project") : m.end("project")])
                text = text[: m.start()]
                continue
            hit = False
            for word, prio in PRIORITY_WORDS.items():
                m = re.search(rf"\s+(?:com\s+|de\s+)?{word}\s*$", n)
                if m:
                    params["priority"] = prio
                    text = text[: m.start()]
                    hit = True
                    break
            if not hit:
                break
        return _clean_slot(text), params

    # ------------------------------------------------------------------ interpretação

    def parse(self, raw: str) -> Intent:  # noqa: C901 (lista de regras, lida de cima para baixo)
        text = self.strip_prefixes(raw)
        n = squash(normalize(text))
        if not n:
            return Intent("control", control="greet")

        def tail(m: re.Match[str], group: str = "x") -> str:
            # Mapeia o grupo da versão «squashed» para o texto original.
            return _map_group(text, n, m, group)

        # --- Controlo da conversa
        if re.fullmatch(
            r"(?:sim|confirmo|confirma|pode ser|podes avancar|pode avancar|avanca|ok|claro|faz isso|quero|esta bem|bora|vamos)(?: (?:sim|quero|claro|pode ser|obrigad[oa]|faz isso|por favor|avanca|vamos la|la))*",
            n,
        ):
            return Intent("control", control="confirm")
        if re.fullmatch(
            r"(?:nao|rejeito|rejeita|nao faz isso|nao quero|negativo|agora nao|mais tarde|depois)(?: (?:obrigad[oa]|agora|por agora|nao))*",
            n,
        ):
            return Intent("control", control="reject")
        if re.fullmatch(r"(?:cancela|cancelar|esquece|para|pare|chega|silencio|cala te|stop|deixa)(?: isso| tudo)?", n):
            return Intent("control", control="cancel")
        if re.search(r"\b(?:repete|repetir|repita|podes repetir|diz outra vez|outra vez)\b", n):
            return Intent("control", control="repeat")
        if re.fullmatch(r"(?:continua|continuar|retoma|retomar)(?: a leitura)?", n):
            return Intent("control", control="resume")
        if re.fullmatch(r"(?:obrigad[oa]|muito obrigad[oa]|valeu|obrigado uaji)", n):
            return Intent("control", control="thanks")
        if re.fullmatch(r"(?:ola|bom dia|boa tarde|boa noite|estas ai|esta ai|tudo bem)", n):
            return Intent("control", control="greet")
        if re.search(r"\b(?:ajuda|o que (?:podes|consegues|sabes) fazer|que comandos)\b", n):
            return Intent("control", control="help")

        # --- Relatórios
        if re.search(
            r"relatorio (?:do (?:meu )?dia|diario|de hoje)|resum\w* (?:o |do )?(?:meu )?(?:dia|trabalho (?:que fiz )?(?:de )?hoje)|o que fiz hoje",
            n,
        ):
            return Intent("tool", "build_report", {"kind": "daily"})
        if re.search(
            r"(?:relatorio|resumo) (?:semanal|da semana)|revisao semanal|produtividade (?:da|desta) semana", n
        ):
            return Intent("tool", "build_report", {"kind": "weekly"})
        if re.search(r"(?:estado|resumo|ponto de situacao) (?:de )?(?:todos )?(?:os |dos )?(?:meus )?projec?tos", n):
            return Intent("tool", "build_report", {"kind": "projects"})
        if re.search(r"(?:principais |que )?problemas|alertas|o que (?:esta|ha) de errado", n):
            return Intent("tool", "build_report", {"kind": "problems"})
        if re.search(r"automac\w+ (?:executad\w+|que (?:correram|foram executadas))(?: hoje)?|automacoes de hoje", n):
            return Intent("tool", "build_report", {"kind": "automations"})
        if re.search(
            r"o que (?:devo|tenho de|tenho que|posso) fazer (?:a seguir|agora|primeiro|depois)"
            r"|(?:tarefas|o) que devo (?:concluir|fazer) primeiro|proxim\w+ (?:passos|accao|accoes|acao|acoes)",
            n,
        ):
            return Intent("tool", "build_report", {"kind": "next_steps"})

        # --- Escrita: tarefas
        m = re.match(
            r"^(?:cria|criar|crie|adiciona|adicionar|acrescenta|regista|registar|nova|novo|mete|poe)"
            r"(?: me)?(?: uma| a)?(?: nova)? tarefa(?: nova)?(?: para| de| chamada| com o titulo| que diz)?\s+(?P<x>.+)$",
            n,
        )
        if m:
            title, mods = self._extract_modifiers(tail(m))
            if not title:
                return Intent("tool", "create_task", mods, missing="title", prompt="Qual é o título da tarefa?")
            return Intent("tool", "create_task", {"title": title, **mods})
        if re.fullmatch(r"(?:cria|criar|adiciona|nova) (?:uma )?tarefa", n):
            return Intent("tool", "create_task", {}, missing="title", prompt="Qual é o título da tarefa?")

        m = re.match(
            r"^(?:conclui|concluir|termina|terminar|marca como (?:concluida|feita)|terminei|acabei|ja fiz)"
            r"(?: a)?(?: tarefa)?\s+(?P<x>.+)$",
            n,
        )
        if m and not re.match(r"^(?:terminar?|termina) (?:a )?(?:sessao de )?foco", n):
            return Intent("tool", "update_task_status", {"task": _clean_slot(tail(m)), "status": "done"})
        m = re.match(
            r"^(?:muda|mudar|passa|passar|coloca|poe|marca)(?: a)?(?: tarefa)?\s+(?P<x>.+?)\s+(?:para|como)\s+(?P<s>"
            + "|".join(STATUS_WORDS)
            + r")$",
            n,
        )
        if m:
            return Intent(
                "tool", "update_task_status", {"task": _clean_slot(tail(m)), "status": STATUS_WORDS[m.group("s")]}
            )
        m = re.match(r"^(?:apaga|apagar|elimina|eliminar|remove|remover|exclui)(?: a)? tarefa\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "delete_task", {"task": _clean_slot(tail(m))})

        # --- Escrita: projectos
        m = re.match(r"^(?:apaga|apagar|elimina|eliminar|remove|exclui)(?: o)? projec?to\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "delete_project", {"project": _clean_slot(tail(m))})
        m = re.match(r"^(?:arquiva|arquivar)(?: o)?(?: projec?to)?\s+(?P<x>.+)$", n)
        if m:
            ref = tail(m)
            if re.fullmatch(THIS_PROJECT, squash(normalize(ref))):
                return Intent("tool", "archive_project", {}, needs_project_context=True)
            return Intent("tool", "archive_project", {"project": _clean_slot(ref)})
        m = re.match(
            r"^(?:cria|criar|crie|novo|abre um novo)(?: um)?(?: novo)? projec?to(?: chamado| com o nome| de)?\s+(?P<x>.+)$",
            n,
        )
        if m:
            return Intent("tool", "create_project", {"name": _clean_slot(tail(m))})

        # --- Escrita: notas e ideias
        m = re.match(
            r"^(?:regista|registar|guarda|guardar|anota|anotar|aponta|apontar|cria|criar|adiciona|nova|tomar nota)"
            r"(?: esta| essa| uma| a| nova)?\s*(?P<k>ideia|nota|decisao)"
            r"(?: nas (?:minhas )?notas)?(?:\s*(?:que|sobre|de|para|:)\s*|\s+)?(?P<x>.*)$",
            n,
        )
        if m:
            kind = {"ideia": "idea", "decisao": "decision"}.get(m.group("k"), "note")
            content = _clean_slot(tail(m)) if m.group("x").strip() else ""
            if not content:
                what = {"idea": "a ideia", "decision": "a decisão"}.get(kind, "o conteúdo da nota")
                return Intent("tool", "create_note", {"kind": kind}, missing="title", prompt=f"Qual é {what}?")
            return Intent("tool", "create_note", {"kind": kind, "title": content[:300], "content": content})

        # --- Escrita: checklists
        m = re.match(
            r"^(?:cria|criar|crie|prepara|faz|gera)(?: uma| me uma)? (?:check ?list|lista de verificacao)(?: para| de| sobre)?\s+(?P<x>.+)$",
            n,
        )
        if m:
            topic = _clean_slot(tail(m))
            return Intent("tool", "create_checklist", {"title": topic, "template": topic})

        # --- Foco e automações
        if re.search(r"^(?:inicia|iniciar|comeca|comecar|liga)(?: uma)?(?: sessao de)? foco", n):
            return Intent("tool", "start_focus", {})
        if re.search(r"^(?:termina|terminar|para|parar|acaba|acabar)(?: a)?(?: sessao de)? foco", n):
            return Intent("tool", "stop_focus", {})
        m = re.match(r"^(?:executa|executar|corre|correr|lanca|lancar)(?: a)? automac\w+\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "run_automation", {"automation": _clean_slot(tail(m))})

        # --- Sistema operativo
        m = re.match(r"^(?:fecha|fechar|encerra|encerrar|sai do|sai da)(?: o| a)?(?: aplicacao| app)?\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "quit_app", {"name": _clean_slot(tail(m))})
        m = re.search(r"(?:volume)\s+(?:a|em|para|no|nos)?\s*(?P<v>\d{1,3})", n) or re.search(
            r"(?:poe|mete|coloca|ajusta|baixa|sobe|muda)(?: o)? volume (?:a|em|para) (?P<v>\d{1,3})", n
        )
        if m:
            return Intent("tool", "set_volume", {"level": min(100, int(m.group("v")))})
        if re.search(r"\b(?:silencia|sem som|mute)\b|tira o som", n):
            return Intent("tool", "set_volume", {"level": 0})
        m = re.match(r"^(?:abre|abrir|vai a|vai ao)(?: o)? (?:site|sitio|pagina|endereco)\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "open_url", {"target": squash(tail(m)).strip(" .")})
        m = re.match(
            r"^(?:pesquisa|procura|busca)(?: por)? (?:na|no) (?:web|internet|google|net)\s+(?:por\s+)?(?P<x>.+)$", n
        ) or re.match(r"^(?:pesquisa|procura|busca)(?: por)?\s+(?P<x>.+?)\s+(?:na|no) (?:web|internet|google|net)$", n)
        if m:
            return Intent("tool", "open_url", {"target": squash(tail(m)).strip(" .")})
        m = re.match(r"^(?:abre|abrir|mostra)(?: a)? pasta\s+(?P<x>.+)$", n)
        if m:
            raw = squash(tail(m)).strip(" .")
            return Intent("tool", "open_path", {"path": raw if raw.startswith(("~", "/")) else f"~/{raw}"})
        m = re.match(
            r"^(?:corre|correr|executa|executar|roda|rodar)(?: o)? (?:comando|no terminal)\s*:?\s+(?P<x>.+)$", n
        ) or re.match(r"^(?:no terminal|terminal)\s*:?\s+(?P<x>.+)$", n)
        if m:
            # O comando é extraído do texto original (com maiúsculas, barras e aspas).
            return Intent("tool", "run_shell", {"command": tail(m).strip()})
        if re.search(r"(?:estado|como esta|como vai)(?: o| do)? (?:sistema|computador|mac|portatil)|\bbateria\b", n):
            return Intent("tool", "system_status", {})
        if re.search(r"(?:que|quais)(?: sao)?(?: as)? (?:aplicacoes|apps|programas)(?: estao| que estao)? abert", n):
            return Intent("tool", "running_apps", {})

        # --- Actividade no computador
        m = re.search(
            r"quanto tempo (?:passei|estive|tenho estado|gastei)(?: hoje)? (?:no|na|em|com o|com a)\s+(?P<x>.+?)(?: hoje)?$",
            n,
        )
        if m:
            return Intent("tool", "activity_today", {"app": _clean_slot(tail(m))})
        if re.search(
            r"o que (?:tenho estado|estive|andei) a fazer|(?:resumo|relatorio) da (?:minha )?actividade|como foi o meu dia no computador|onde passei o (?:meu )?tempo",
            n,
        ):
            return Intent("tool", "activity_today", {})
        if re.search(
            r"(?:os )?meus (?:habitos|padroes)|como (?:costumo|e que costumo) trabalhar|quando (?:costumo|sou mais) produtiv",
            n,
        ):
            return Intent("tool", "activity_patterns", {})
        if re.search(
            r"commits?(?: de| que fiz| fiz| que fiz)? hoje|commits? (?:que )?fiz|o que fiz no git|(?:meus|os) commits",
            n,
        ):
            return Intent("tool", "git_today", {})

        # --- Consultas
        if re.search(r"automac\w+ (?:que )?(?:falhad\w+|falharam|com erro)", n):
            return Intent("tool", "list_automation_runs", {"status": "failed", "period": "week"})
        if re.search(r"projec?tos? .*mais atrasado|mais atrasado dos (?:meus )?projec?tos", n):
            return Intent("tool", "build_report", {"kind": "projects"})
        m = re.search(
            r"(?:o que (?:esta|anda) a bloquear|bloqueios? d[oe]|porque (?:esta|e que esta) bloqueado)\s*(?P<x>.*)$", n
        )
        if m:
            ref = squash(normalize(tail(m)))
            if not ref or re.fullmatch(THIS_PROJECT, ref):
                return Intent("tool", "explain_project_blockers", {}, needs_project_context=True)
            return Intent(
                "tool",
                "explain_project_blockers",
                {"project": _clean_slot(re.sub(r"^(?:o |do )?projec?to ", "", tail(m)))},
            )
        m = re.search(r"(?:le|ler|leia|da me|diz me)?\s*(?:o )?resumo (?:d[oe]ste|desse|do) projec?to\s*(?P<x>.*)$", n)
        if m:
            ref = tail(m).strip()
            if not ref:
                return Intent("tool", "get_project", {}, needs_project_context=True)
            return Intent("tool", "get_project", {"project": _clean_slot(ref)})
        m = re.match(r"^como (?:esta|vai) o projec?to\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "get_project", {"project": _clean_slot(tail(m))})
        if re.search(r"tarefas? (?:prioritari\w+|mais importantes|urgentes)|prioridades (?:de|para) hoje", n):
            return Intent("tool", "build_report", {"kind": "next_steps"})
        if re.search(r"tarefas? atrasad\w+|o que esta atrasado", n):
            return Intent("tool", "list_tasks", {"due": "overdue"})
        if re.search(r"tarefas? (?:de|para) hoje|(?:prazos?|vence) hoje", n):
            return Intent("tool", "list_tasks", {"due": "today"})
        if re.search(r"tarefas? (?:desta|da|para esta) semana", n):
            return Intent("tool", "list_tasks", {"due": "week"})
        m = re.search(r"tarefas? do projec?to\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "list_tasks", {"project": _clean_slot(tail(m))})
        if re.search(r"\b(?:agenda|compromissos|reunioes|calendario)\b", n):
            day = "amanha" if "amanha" in n else "hoje"
            return Intent("tool", "get_agenda", {"day": day})
        if re.search(r"\b(?:desempenho|produtividade|metricas|tempo de foco|quanto foco)\b", n):
            period = "today" if "hoje" in n else ("month" if "mes" in n.split() else "week")
            return Intent("tool", "get_metrics", {"period": period})
        if re.search(r"(?:quais|que|lista|mostra)\w* (?:sao )?(?:os )?(?:meus )?projec?tos", n):
            return Intent("tool", "list_projects", {})
        m = re.match(r"^(?:pesquisa|pesquisar|procura|procurar|encontra)(?: por)?\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "search", {"query": _clean_slot(tail(m))})
        m = re.match(r"^(?:abre|abrir|mostra(?: me)?|vai para|ir para|leva me (?:a|para)|navega para)\s+(?P<x>.+)$", n)
        if m:
            return Intent("tool", "navigate", {"target": squash(tail(m)).strip(" .")})
        if re.search(r"(?:resumo|visao geral|ponto de situacao|como estou|como esta tudo)", n):
            return Intent("tool", "get_overview", {})
        return Intent("unknown")


def _map_group(original: str, squashed: str, m: re.Match[str], group: str) -> str:
    """Converte um grupo encontrado no texto «squashed» para o excerto do texto original."""
    start, end = m.start(group), m.end(group)
    if start < 0:
        return ""
    folded = normalize(original)
    # Índice do i-ésimo carácter não-espaço «squashed» → índice no original.
    idx: list[int] = []
    prev_space = True
    for i, c in enumerate(folded):
        if c == " ":
            if not prev_space:
                idx.append(i)
            prev_space = True
        else:
            idx.append(i)
            prev_space = False
    if start >= len(idx):
        return ""
    o_start = idx[start]
    o_end = idx[end - 1] + 1 if end - 1 < len(idx) else len(original)
    return original[o_start:o_end]
