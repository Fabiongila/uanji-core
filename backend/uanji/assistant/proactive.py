"""Iniciativa do assistente: fala com o utilizador sem esperar que ele carregue num botão.

A cada 30 s avalia regras sobre dados reais (tarefas, agenda, automações, foco) e, se o
monitor de actividade estiver ligado, sobre o que a pessoa está a fazer no computador.
No máximo uma mensagem por avaliação, com limites para não ser intrusivo:

- intervalo mínimo entre mensagens (intensidade: baixa 45 min, normal 20 min, alta 8 min),
  excepto avisos com hora marcada (compromissos e prazos a terminar);
- nunca nas horas de silêncio (Definições → Notificações);
- não fala durante reuniões (Zoom, Teams, FaceTime…) nem enquanto está a ouvir ou a falar;
- com o monitor ligado, espera que a pessoa esteja ao computador;
- cada mensagem é única (não repete o mesmo aviso, mesmo depois de reiniciar).

Quando a mensagem termina com uma pergunta («Quer que leia as prioridades?»), regista uma
oferta: a resposta «sim» (voz ou texto) executa-a. Com a escuta ligada, o microfone fica a
ouvir a resposta durante alguns segundos, como numa conversa.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import runtime
from ..activity import insights
from ..activity import monitor as activity
from ..models import Automation, AutomationRun, Event, FocusSession, Notification, Project, Task
from ..services import metrics
from ..services import notifications as notification_service
from ..services.common import get_all_settings, local_tz
from .persona import Persona

log = logging.getLogger(__name__)

GAP_MINUTES = {"low": 45, "normal": 20, "high": 8}
SWITCH_LIMIT = {"low": 30, "normal": 22, "high": 15}
URGENT = {"events", "deadlines"}


@dataclass
class Nudge:
    rule: str
    key: str
    text: str
    offer: tuple[str, dict[str, Any]] | None = None
    offer_label: str = ""
    level: str = "info"
    link: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "text": self.text,
            "offer": {"tool": self.offer[0], "label": self.offer_label} if self.offer else None,
            "link": self.link,
        }


def _in_quiet(now_local: datetime, start: str, end: str) -> bool:
    try:
        s = time.fromisoformat(start)
        e = time.fromisoformat(end)
    except ValueError:
        return False
    t = now_local.time()
    return (s <= t or t < e) if s > e else (s <= t < e)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class ProactiveEngine:
    def __init__(
        self,
        deliver: Callable[[Nudge], bool] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        live: Callable[[], activity.LiveState | None] | None = None,
    ) -> None:
        self.deliver = deliver
        self.clock = clock
        self.live = live or (lambda: activity.get().state if activity.get().enabled else None)
        self.last_at: datetime | None = None
        self.started_at = clock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ ciclo

    def start(self, interval: float = 30.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            self._stop.wait(20)
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    log.exception("Falha nas regras de iniciativa do assistente")
                self._stop.wait(interval)

        self._thread = threading.Thread(target=loop, name="uanji-proactive", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> Nudge | None:
        """Avalia as regras e entrega no máximo uma mensagem. Devolve a mensagem entregue."""
        now = self.clock()
        with runtime.get_database().session() as db:
            settings = get_all_settings(db)
            cfg = settings["proactive"]
            if not cfg.get("enabled", True):
                return None
            tz = local_tz(db)
            local_now = now.astimezone(tz)
            notif = settings["notifications"]
            if _in_quiet(local_now, str(notif.get("quiet_start", "22:00")), str(notif.get("quiet_end", "07:00"))):
                return None
            live = self.live()
            if live is not None and live.idle_seconds > 120:
                return None  # a pessoa não está ao computador
            gap_ok = self.last_at is None or now - self.last_at >= timedelta(
                minutes=GAP_MINUTES.get(str(cfg.get("intensity", "normal")), 20)
            )
            rules: dict[str, bool] = cfg.get("rules", {})
            persona = Persona.from_settings(settings)
            for rule, fn in self._rules():
                if not rules.get(rule, True) or (not gap_ok and rule not in URGENT):
                    continue
                nudge = fn(db, now, local_now, live, settings, persona)
                if nudge is None or self._fired(db, nudge.key):
                    continue
                if self.deliver is not None and not self.deliver(nudge):
                    return None  # ocupado (a falar/ouvir): tenta na próxima avaliação
                notification_service.create(
                    db,
                    category="assistant",
                    title=nudge.text[:300],
                    level=nudge.level,
                    link=nudge.link or "/assistant",
                    dedupe_key=f"proactive:{nudge.key}",
                    respect_preferences=False,
                )
                self.last_at = now
                return nudge
        return None

    @staticmethod
    def _fired(db: Session, key: str) -> bool:
        return db.scalar(select(Notification.id).where(Notification.dedupe_key == f"proactive:{key}")) is not None

    def _rules(self) -> list[tuple[str, Callable[..., Nudge | None]]]:
        return [
            ("events", self._event_soon),
            ("deadlines", self._deadline_soon),
            ("return", self._welcome_back),
            ("morning", self._morning),
            ("automations", self._failed_automation),
            ("focus", self._long_focus),
            ("breaks", self._long_streak),
            ("context_switch", self._context_switching),
            ("suggestions", self._suggest_from_activity),
            ("end_of_day", self._end_of_day),
        ]

    # ------------------------------------------------------------------ regras

    def _event_soon(self, db: Session, now: datetime, local_now: datetime, *_: Any) -> Nudge | None:
        ev = db.scalar(
            select(Event)
            .where(Event.start_at > now, Event.start_at <= now + timedelta(minutes=10))
            .order_by(Event.start_at)
        )
        if ev is None:
            return None
        mins = max(1, int((ev.start_at - now).total_seconds() // 60))
        return Nudge(
            "events", f"event:{ev.id}", f"Daqui a {mins} minutos tem «{ev.title}».", link="/agenda", level="warning"
        )

    def _deadline_soon(self, db: Session, now: datetime, *_: Any) -> Nudge | None:
        t = db.scalar(
            select(Task)
            .where(
                Task.status != "done",
                Task.archived_at.is_(None),
                Task.due_at > now,
                Task.due_at <= now + timedelta(minutes=60),
            )
            .order_by(Task.due_at)
        )
        if t is None:
            return None
        assert t.due_at is not None
        mins = max(1, int((t.due_at - now).total_seconds() // 60))
        return Nudge(
            "deadlines",
            f"deadline:{t.id}",
            f"A tarefa «{t.title}» vence daqui a {mins} minutos. Quer marcá-la como concluída?",
            offer=("update_task_status", {"task": t.id, "status": "done"}),
            offer_label="Marcar como concluída",
            link=f"/tasks/{t.id}",
            level="warning",
        )

    def _welcome_back(
        self,
        db: Session,
        now: datetime,
        local_now: datetime,
        live: activity.LiveState | None,
        settings: Any,
        persona: Persona,
    ) -> Nudge | None:
        if live is None or live.returned_at is None or live.returned_after < 20 * 60:
            return None
        if now - live.returned_at > timedelta(minutes=3):
            return None
        away = insights.fmt_duration(live.returned_after)
        next_task = db.scalar(
            select(Task)
            .where(
                Task.status != "done",
                Task.archived_at.is_(None),
                Task.due_at > now,
                Task.due_at <= now + timedelta(hours=3),
            )
            .order_by(Task.due_at)
        )
        text = f"{persona.welcome()} Esteve fora {away}."
        if next_task is not None:
            text += f" A próxima tarefa com prazo é «{next_task.title}»."
        text += " Quer que diga o que ficou pendente?"
        return Nudge(
            "return",
            f"return:{live.returned_at.isoformat()}",
            text,
            offer=("build_report", {"kind": "next_steps"}),
            offer_label="Ver o que ficou pendente",
        )

    def _morning(
        self,
        db: Session,
        now: datetime,
        local_now: datetime,
        live: activity.LiveState | None,
        settings: Any,
        persona: Persona,
    ) -> Nudge | None:
        if not (5 <= local_now.hour < 13):
            return None
        d = metrics.dashboard(db)
        c = d["counters"]
        greet = "Bom dia" if local_now.hour < 12 else "Boa tarde"
        greet = persona.address_phrase(greet + ".")
        parts = [greet]
        due_today = sum(
            1 for t in d["upcoming"] if t.due_at and t.due_at.astimezone(local_now.tzinfo).date() == local_now.date()
        )
        if c["pending_tasks"]:
            parts.append(
                f"Tem {_plural(c['pending_tasks'], 'tarefa pendente', 'tarefas pendentes')}"
                + (f", {_plural(c['overdue_tasks'], 'atrasada', 'atrasadas')}" if c["overdue_tasks"] else "")
                + (f" e {_plural(due_today, 'com prazo hoje', 'com prazo hoje')}" if due_today else "")
                + "."
            )
            if d["priority_tasks"]:
                parts.append(f"A prioridade parece ser «{d['priority_tasks'][0].title}».")
        else:
            parts.append("Não tem tarefas pendentes.")
        start, end = now, now + timedelta(hours=14)
        first_event = db.scalar(
            select(Event).where(Event.start_at >= start, Event.start_at < end).order_by(Event.start_at)
        )
        if first_event is not None:
            parts.append(
                f"O primeiro compromisso é às {first_event.start_at.astimezone(local_now.tzinfo).strftime('%H:%M')}: «{first_event.title}»."
            )
        pat = insights.patterns(db)
        if pat["avg_start"] and pat["days_with_data"] >= 3:
            h, m = map(int, str(pat["avg_start"]).split(":"))
            diff = (local_now.hour * 60 + local_now.minute) - (h * 60 + m)
            if diff <= -45:
                parts.append("Começou mais cedo do que o habitual.")
            elif diff >= 90:
                parts.append("Hoje começou mais tarde do que o habitual.")
            if pat["peak_hours"]:
                parts.append(
                    f"As suas horas mais intensas costumam ser às {pat['peak_hours'][0]}h; pode ser boa altura para a tarefa mais exigente."
                )
        if c["pending_tasks"]:
            parts.append("Quer que leia as prioridades?")
            offer: tuple[str, dict[str, Any]] | None = ("build_report", {"kind": "next_steps"})
        else:
            offer = None
        return Nudge(
            "morning",
            f"morning:{local_now.date().isoformat()}",
            " ".join(parts),
            offer=offer,
            offer_label="Ler as prioridades",
        )

    def _failed_automation(self, db: Session, now: datetime, *_: Any) -> Nudge | None:
        row = db.execute(
            select(AutomationRun, Automation.name)
            .join(Automation, Automation.id == AutomationRun.automation_id)
            .where(AutomationRun.status == "failed", AutomationRun.started_at >= self.started_at - timedelta(hours=12))
            .order_by(AutomationRun.started_at.desc())
        ).first()
        if row is None:
            return None
        run, name = row
        return Nudge(
            "automations",
            f"run:{run.id}",
            f"A automação «{name}» falhou: {run.error[:160] or 'sem detalhe'}.",
            link=f"/automations/{run.automation_id}",
            level="error",
        )

    def _long_focus(self, db: Session, now: datetime, *_: Any) -> Nudge | None:
        f = db.scalar(select(FocusSession).where(FocusSession.ended_at.is_(None)))
        if f is None:
            return None
        mins = int((now - f.started_at).total_seconds() // 60)
        if mins < 50:
            return None
        block = mins // 50
        return Nudge(
            "focus",
            f"focus:{f.id}:{block}",
            f"Está em sessão de foco há {mins} minutos. Quer terminar e registar a sessão?",
            offer=("stop_focus", {}),
            offer_label="Terminar o foco",
        )

    def _long_streak(
        self, db: Session, now: datetime, local_now: datetime, live: activity.LiveState | None, *_: Any
    ) -> Nudge | None:
        if live is None or live.active_since is None:
            return None
        mins = int((now - live.active_since).total_seconds() // 60)
        if mins < 90:
            return None
        return Nudge(
            "breaks",
            f"break:{live.active_since.isoformat()}",
            f"Está a trabalhar há {insights.fmt_duration(mins * 60)} sem pausa. Uns minutos longe do ecrã ajudam a manter o ritmo.",
        )

    def _context_switching(
        self, db: Session, now: datetime, local_now: datetime, live: activity.LiveState | None, settings: Any, *_: Any
    ) -> Nudge | None:
        if live is None:
            return None
        limit = SWITCH_LIMIT.get(str(settings["proactive"].get("intensity", "normal")), 22)
        n = live.switches_in(15, now)
        if n < limit or db.scalar(select(FocusSession.id).where(FocusSession.ended_at.is_(None))):
            return None
        return Nudge(
            "context_switch",
            f"switch:{local_now.strftime('%Y-%m-%d %H')}",
            f"Mudou de aplicação {n} vezes nos últimos 15 minutos. Quer iniciar uma sessão de foco para se concentrar numa coisa?",
            offer=("start_focus", {}),
            offer_label="Iniciar foco",
        )

    def _suggest_from_activity(
        self, db: Session, now: datetime, local_now: datetime, live: activity.LiveState | None, *_: Any
    ) -> Nudge | None:
        """Adapta-se ao que a pessoa está a fazer: liga o trabalho no computador aos projectos."""
        if live is None or live.since is None or live.category != "desenvolvimento":
            return None
        mins = int((now - live.since).total_seconds() // 60)
        if mins < 30:
            return None
        day = local_now.date().isoformat()
        if live.project_id:
            if db.scalar(select(FocusSession.id).where(FocusSession.ended_at.is_(None))):
                return None
            p = db.get(Project, live.project_id)
            if p is None:
                return None
            return Nudge(
                "suggestions",
                f"focus-project:{p.id}:{day}",
                f"Está a trabalhar no projecto {p.name} há {mins} minutos. Quer que registe uma sessão de foco neste projecto?",
                offer=("start_focus", {"project": p.id}),
                offer_label="Iniciar foco no projecto",
            )
        if live.context:
            return Nudge(
                "suggestions",
                f"new-project:{live.context}",
                f"Está há {mins} minutos na pasta «{live.context}», que não corresponde a nenhum projecto do UANJI. Quer que crie um projecto com esse nome?",
                offer=("create_project", {"name": live.context}),
                offer_label="Criar projecto",
            )
        return None

    def _end_of_day(
        self, db: Session, now: datetime, local_now: datetime, live: Any, settings: Any, *_: Any
    ) -> Nudge | None:
        try:
            review = time.fromisoformat(str(settings["notifications"].get("daily_review_time", "18:00")))
        except ValueError:
            review = time(18, 0)
        if local_now.time() < review or local_now.hour >= 23:
            return None
        d = metrics.dashboard(db)
        today = insights.summarize(db)
        if not d["counters"]["done_today"] and not today["has_data"]:
            return None
        return Nudge(
            "end_of_day",
            f"eod:{local_now.date().isoformat()}",
            f"Está a chegar ao fim do dia: concluiu {_plural(d['counters']['done_today'], 'tarefa', 'tarefas')} hoje. Quer ouvir o resumo do dia?",
            offer=("build_report", {"kind": "daily"}),
            offer_label="Ouvir o resumo do dia",
        )


_engine: ProactiveEngine | None = None


def get() -> ProactiveEngine | None:
    return _engine


def set_engine(engine: ProactiveEngine | None) -> None:
    global _engine
    if _engine is not None and engine is not _engine:
        _engine.stop()
    _engine = engine
