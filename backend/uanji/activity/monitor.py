"""Monitor de actividade no computador (opcional, só local).

O que é recolhido, a cada ``sample_seconds`` (15 s por omissão):
- aplicação em primeiro plano (nome e identificador) — sem permissões especiais;
- tempo desde a última interacção (teclado/rato) — só o número de segundos, nunca as teclas;
- contexto conhecido sem permissões: pasta aberta no VS Code (ficheiro de estado do próprio editor);
- título da janela, apenas se activado E se o macOS autorizar «Gravação de ecrã».

Amostras consecutivas iguais são agrupadas numa sessão (``ActivitySession``). A inactividade
(acima de ``idle_seconds``) fecha a sessão e não conta como tempo activo. Aplicações excluídas
não são registadas.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from sqlalchemy import delete, select

from .. import runtime
from ..models import ActivitySession, Project
from ..services.common import get_all_settings

log = logging.getLogger(__name__)

CATEGORY_LABEL = {
    "desenvolvimento": "Desenvolvimento",
    "navegacao": "Navegação web",
    "comunicacao": "Comunicação",
    "reunioes": "Reuniões",
    "escritorio": "Documentos e escritório",
    "design": "Design",
    "media": "Música e vídeo",
    "sistema": "Sistema",
    "uanji": "UANJI CORE",
    "outros": "Outros",
}
# Palavras no nome/identificador → categoria (a primeira que corresponder).
CATEGORY_RULES: list[tuple[str, str]] = [
    (r"zoom|teams|facetime|meet|webex|skype|discord", "reunioes"),
    (r"uanji", "uanji"),
    (
        r"code|xcode|pycharm|intellij|webstorm|terminal|iterm|warp|sublime|cursor|android studio|docker|postman|tableplus|dbeaver|jupyter|rstudio|spyder|anaconda",
        "desenvolvimento",
    ),
    (r"chrome|safari|firefox|edge|brave|opera|arc", "navegacao"),
    (r"whatsapp|telegram|slack|mail|correio|outlook|messages|mensagens|signal", "comunicacao"),
    (
        r"word|excel|powerpoint|pages|numbers|keynote|notes|notas|libreoffice|preview|pré-visualização|acrobat|notion|obsidian",
        "escritorio",
    ),
    (r"figma|sketch|photoshop|illustrator|affinity|canva|blender", "design"),
    (r"vlc|spotify|music|música|tv|quicktime|youtube|iina", "media"),
    (r"finder|system settings|definições do sistema|activity monitor|monitor de actividade|app store", "sistema"),
]
MEETING_CATEGORIES = {"reunioes"}


def categorize(app: str, bundle_id: str = "") -> str:
    key = f"{app} {bundle_id}".lower()
    for pattern, cat in CATEGORY_RULES:
        if re.search(pattern, key):
            return cat
    return "outros"


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def match_project(text: str, projects: list[tuple[str, str]]) -> str | None:
    """Associa um contexto (ex.: «Q360-Linha-Saude-backend») a um projecto pelo nome.

    Corresponde se o nome normalizado estiver contido no contexto, ou se partilharem uma palavra
    distintiva (com dígitos ou ≥ 5 letras). Ambiguidade → nenhuma associação.
    """
    t = _norm(text)
    if not t:
        return None
    words = set(t.split())
    hits = []
    for pid, name in projects:
        n = _norm(name)
        if not n:
            continue
        distinctive = {w for w in n.split() if any(c.isdigit() for c in w) or len(w) >= 5}
        if f" {n} " in f" {t} " or (distinctive & words):
            hits.append(pid)
    return hits[0] if len(hits) == 1 else None


@dataclass
class Sample:
    app: str
    bundle_id: str = ""
    title: str = ""
    context: str = ""
    idle_seconds: float = 0.0


# --------------------------------------------------------------------------- Sondas do macOS


def _vscode_folder() -> str:
    """Pasta da janela activa do VS Code, a partir do ficheiro de estado do editor."""
    p = Path.home() / "Library/Application Support/Code/User/globalStorage/storage.json"
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return ""
    win = (data.get("windowsState") or {}).get("lastActiveWindow") or {}
    folder = win.get("folder") or (win.get("workspaceIdentifier") or {}).get("configURIPath") or ""
    return Path(unquote(urlparse(folder).path)).name if folder else ""


def probe_macos(capture_titles: bool) -> Sample | None:
    try:
        import AppKit  # type: ignore[import-untyped,import-not-found,unused-ignore]
        import Quartz  # type: ignore[import-untyped,import-not-found,unused-ignore]
    except Exception:
        return None
    idle = float(
        Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType
        )
    )
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID
    )
    front = next((w for w in wins or [] if w.get("kCGWindowLayer") == 0 and w.get("kCGWindowOwnerName")), None)
    if front is None:
        return Sample("", idle_seconds=idle)
    app = str(front.get("kCGWindowOwnerName") or "")
    bundle = ""
    pid = front.get("kCGWindowOwnerPID")
    if pid:
        ra = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
        if ra is not None:
            bundle = str(ra.bundleIdentifier() or "")
            app = str(ra.localizedName() or app)
    title = str(front.get("kCGWindowName") or "") if capture_titles else ""
    context = _vscode_folder() if bundle == "com.microsoft.VSCode" else ""
    return Sample(app, bundle, title[:500], context, idle)


# --------------------------------------------------------------------------- Monitor


@dataclass
class LiveState:
    """Estado em memória usado pelas regras de iniciativa do assistente."""

    app: str = ""
    category: str = ""
    context: str = ""
    project_id: str | None = None
    since: datetime | None = None
    idle_seconds: float = 0.0
    active_since: datetime | None = None  # início do período activo contínuo
    returned_after: float = 0.0  # segundos de ausência no último regresso
    returned_at: datetime | None = None
    switches: deque[datetime] = field(default_factory=lambda: deque(maxlen=200))

    def switches_in(self, minutes: int, now: datetime) -> int:
        return sum(1 for t in self.switches if now - t <= timedelta(minutes=minutes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app,
            "category": self.category,
            "context": self.context,
            "project_id": self.project_id,
            "since": self.since.isoformat() if self.since else None,
            "idle_seconds": round(self.idle_seconds),
            "active_since": self.active_since.isoformat() if self.active_since else None,
        }


class ActivityMonitor:
    def __init__(
        self,
        probe: Callable[[bool], Sample | None] = probe_macos,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.probe = probe
        self.clock = clock
        self.state = LiveState()
        self.enabled = False
        self.last_error = ""
        self._current_id: str | None = None
        self._current_key: tuple[str, str, str] | None = None
        self._last_app = ""
        self._was_idle_since: datetime | None = None
        self._projects: list[tuple[str, str]] = []
        self._projects_at = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ ciclo

    def settings(self) -> dict[str, Any]:
        with runtime.get_database().session() as db:
            return dict(get_all_settings(db)["activity"])

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.enabled = True
        self._thread = threading.Thread(target=self._run, name="uanji-activity", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.enabled = False
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        self._close()

    def _run(self) -> None:
        while not self._stop.is_set():
            cfg = self.settings()
            try:
                self.tick(cfg)
                self.last_error = ""
            except Exception as e:
                log.exception("Falha no monitor de actividade")
                self.last_error = str(e)[:200]
            self._stop.wait(max(5, int(cfg.get("sample_seconds", 15))))

    # ------------------------------------------------------------------ amostragem

    def _project_names(self) -> list[tuple[str, str]]:
        if time.monotonic() - self._projects_at > 300:
            with runtime.get_database().session() as db:
                self._projects = [
                    (p.id, p.name) for p in db.scalars(select(Project).where(Project.archived_at.is_(None)))
                ]
            self._projects_at = time.monotonic()
        return self._projects

    def tick(self, cfg: dict[str, Any]) -> None:
        """Uma amostra: actualiza o estado em memória e a sessão na base de dados."""
        now = self.clock()
        sample = self.probe(bool(cfg.get("capture_titles")))
        if sample is None:
            self.last_error = "Monitor indisponível neste sistema (requer macOS com PyObjC)."
            return
        st = self.state
        st.idle_seconds = sample.idle_seconds
        idle_limit = float(cfg.get("idle_seconds", 300))
        if sample.idle_seconds >= idle_limit:
            if self._was_idle_since is None:
                self._was_idle_since = now - timedelta(seconds=sample.idle_seconds)
                self._close()
                st.active_since = None
            return
        if self._was_idle_since is not None:
            st.returned_after = (now - self._was_idle_since).total_seconds()
            st.returned_at = now
            self._was_idle_since = None
        if st.active_since is None:
            st.active_since = now - timedelta(seconds=sample.idle_seconds)
        excluded = {a.lower() for a in cfg.get("excluded_apps", [])}
        if not sample.app or sample.app.lower() in excluded:
            self._close()
            st.app, st.category, st.context, st.project_id = "", "", "", None
            return
        key = (sample.app, sample.context, sample.title)
        if key != self._current_key:
            if self._last_app and self._last_app != sample.app:
                st.switches.append(now)
            if self._last_app != sample.app:
                self._app_activated(sample.app, now)
            self._last_app = sample.app
            self._close()
            category = categorize(sample.app, sample.bundle_id)
            project_id = match_project(f"{sample.context} {sample.title}", self._project_names())
            with runtime.get_database().session() as db:
                row = ActivitySession(
                    app=sample.app[:200],
                    bundle_id=sample.bundle_id[:200],
                    category=category,
                    context=sample.context[:300],
                    title=sample.title[:500],
                    project_id=project_id,
                    started_at=now,
                    ended_at=now,
                    seconds=0,
                )
                db.add(row)
                db.flush()
                self._current_id = row.id
            self._current_key = key
            st.app, st.category, st.context, st.project_id, st.since = (
                sample.app,
                category,
                sample.context,
                project_id,
                now,
            )
            return
        with runtime.get_database().session() as db:
            row2 = db.get(ActivitySession, self._current_id) if self._current_id else None
            if row2 is not None:
                row2.ended_at = now
                row2.seconds = int((now - row2.started_at).total_seconds())

    @staticmethod
    def _app_activated(app: str, now: datetime) -> None:
        """Gatilho de automações «quando abro a aplicação X» (em segundo plano, sem atrasar a amostra)."""
        from ..automation import engine

        threading.Thread(target=engine.on_app_activated, args=(app, now), daemon=True).start()

    def _close(self) -> None:
        self._current_id = None
        self._current_key = None

    # ------------------------------------------------------------------ manutenção

    @staticmethod
    def purge(days: int | None = None) -> int:
        with runtime.get_database().session() as db:
            keep = int(get_all_settings(db)["activity"].get("retention_days", 30)) if days is None else days
            stmt = delete(ActivitySession)
            if keep > 0:
                stmt = stmt.where(ActivitySession.started_at < datetime.now(UTC) - timedelta(days=keep))
            return int(getattr(db.execute(stmt), "rowcount", 0) or 0)


_monitor: ActivityMonitor | None = None
_lock = threading.Lock()


def get() -> ActivityMonitor:
    global _monitor
    with _lock:
        if _monitor is None:
            _monitor = ActivityMonitor()
        return _monitor


def set_monitor(m: ActivityMonitor | None) -> None:
    global _monitor
    with _lock:
        if _monitor is not None and m is not _monitor:
            _monitor.stop()
        _monitor = m


def apply_settings(cfg: dict[str, Any]) -> None:
    m = get()
    if cfg.get("enabled") and not m.enabled:
        m.start()
    elif not cfg.get("enabled") and m.enabled:
        m.stop()
