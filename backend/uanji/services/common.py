"""Utilitários partilhados pelos serviços: histórico, índice de pesquisa e definições."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db import Base
from ..errors import NotFound
from ..models import Activity, Setting

T = TypeVar("T", bound=Base)

ENTITY_LABELS = {
    "project": "Projecto",
    "task": "Tarefa",
    "note": "Nota",
    "event": "Evento",
    "checklist": "Checklist",
    "automation": "Automação",
    "secret": "Segredo",
    "backup": "Backup",
    "integration": "Integração",
    "review": "Revisão",
    "settings": "Definições",
}


def get_or_404[T: Base](db: Session, model: type[T], id_: str) -> T:
    obj = db.get(model, id_)
    if obj is None:
        label = getattr(model, "__tablename__", "registo")
        raise NotFound(f"Registo não encontrado ({label}).", {"id": id_})
    return obj


def log_activity(
    db: Session,
    entity_type: str,
    entity_id: str,
    action: str,
    summary: str,
    data: dict[str, Any] | None = None,
    sensitive: bool = False,
) -> None:
    db.add(
        Activity(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary[:500],
            data=data or {},
            sensitive=sensitive,
        )
    )


# --------------------------------------------------------------------------- Pesquisa


def _is_fts(db: Session) -> bool:
    row = db.execute(text("SELECT sql FROM sqlite_master WHERE name = 'search_index'")).scalar()
    return bool(row and "fts5" in str(row).lower())


def index_entity(db: Session, entity_type: str, entity_id: str, title: str, body: str) -> None:
    db.execute(
        text("DELETE FROM search_index WHERE entity_type = :t AND entity_id = :i"),
        {"t": entity_type, "i": entity_id},
    )
    db.execute(
        text("INSERT INTO search_index (entity_type, entity_id, title, body) VALUES (:t, :i, :ti, :b)"),
        {"t": entity_type, "i": entity_id, "ti": title, "b": body},
    )


def unindex_entity(db: Session, entity_type: str, entity_id: str) -> None:
    db.execute(
        text("DELETE FROM search_index WHERE entity_type = :t AND entity_id = :i"),
        {"t": entity_type, "i": entity_id},
    )


_TOKEN = re.compile(r"[\w\-]+", re.UNICODE)


def _fts_query(q: str) -> str:
    # Cada termo é citado (evita injecção de sintaxe FTS) e usa prefixo.
    tokens = [t.replace('"', "") for t in _TOKEN.findall(q)]
    return " ".join(f'"{t}"*' for t in tokens if t)


def search(db: Session, q: str, types: list[str] | None = None, limit: int = 30) -> list[dict[str, Any]]:
    q = q.strip()
    if not q:
        return []
    params: dict[str, Any] = {"limit": limit}
    type_clause = ""
    if types:
        placeholders = ", ".join(f":ty{i}" for i in range(len(types)))
        type_clause = f" AND entity_type IN ({placeholders})"
        params.update({f"ty{i}": t for i, t in enumerate(types)})

    if _is_fts(db):
        match = _fts_query(q)
        if not match:
            return []
        params["m"] = match
        sql = (
            "SELECT entity_type, entity_id, title, "  # noqa: S608 (apenas marcadores :ty0..)
            "snippet(search_index, 3, '[', ']', '…', 12) AS snippet "
            f"FROM search_index WHERE search_index MATCH :m{type_clause} "
            "ORDER BY bm25(search_index, 0, 0, 5.0, 1.0) LIMIT :limit"
        )
    else:
        params["like"] = f"%{q}%"
        sql = (
            "SELECT entity_type, entity_id, title, substr(body, 1, 120) AS snippet FROM search_index "  # noqa: S608
            f"WHERE (title LIKE :like OR body LIKE :like){type_clause} LIMIT :limit"
        )
    rows = db.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def search_engine_name(db: Session) -> str:
    return "fts5" if _is_fts(db) else "like"


# --------------------------------------------------------------------------- Definições

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "uanji-dark",
    "reduced_motion": False,
    "timezone": "Africa/Luanda",
    "notifications": {
        "enabled": True,
        "native": False,
        "categories": {
            "deadline": True,
            "overdue": True,
            "review": True,
            "automation": True,
            "backup": True,
        },
        "deadline_hours": 24,
        "quiet_start": "22:00",
        "quiet_end": "07:00",
        "daily_review_time": "18:00",
        "weekly_review_day": 4,  # sexta-feira (0 = segunda)
    },
    "backups": {"automatic": True, "interval_hours": 24, "keep": 10},
    "assistant": {
        "provider": "none",
        "model": "",
        "base_url": "",
        "secret_id": None,
        # Confirmação antes de criar (tarefas, notas…) e antes de alterar dados existentes.
        # Acções destrutivas pedem sempre confirmação.
        "confirm_creates": False,
        "confirm_updates": True,
        # Retenção do histórico de conversa (dias; 0 = não guardar) e turnos usados como contexto.
        "history_days": 30,
        "context_turns": 12,
    },
    "voice": {
        # Escuta contínua da palavra de activação. Desligada por omissão: o microfone só é
        # aberto quando o utilizador a activa (ou carrega no botão do microfone).
        "listening": False,
        "wake_word": "UAJI",
        "sensitivity": 1.0,
        "greeting": "Estou aqui. Em que posso ajudar?",
        "tts_enabled": True,
        "voice": "Joana",
        "rate": 185,
        "volume": 0.9,
        "language": "pt-PT",
        "follow_up_seconds": 8,
    },
    "persona": {"address": "neutral", "custom": ""},
    # Monitor de actividade no computador: desligado por omissão (opt-in), só local.
    "activity": {
        "enabled": False,
        "sample_seconds": 15,
        "idle_seconds": 300,
        "capture_titles": False,
        "excluded_apps": ["1Password", "Bitwarden", "Keychain Access", "Acesso a Porta-chaves", "Palavras-passe"],
        "retention_days": 30,
        "git_folders": [],
    },
    # Iniciativa do assistente: fala sem ser chamado, com limites.
    "proactive": {
        "enabled": True,
        "voice": True,
        "intensity": "normal",  # low | normal | high
        "rules": {
            "morning": True,
            "return": True,
            "deadlines": True,
            "events": True,
            "breaks": True,
            "focus": True,
            "context_switch": True,
            "end_of_day": True,
            "automations": True,
            "suggestions": True,
        },
    },
    # Acções no sistema operativo pedidas ao assistente.
    "system": {"allow_apps": True, "confirm_system": False, "allow_shell": False},
    "appearance": {
        "theme": "uanji-dark",  # uanji-dark | abyss | amber | contrast | light
        "accent": "cyan",  # cyan | blue | amber | emerald | violet
        "density": "comfortable",  # comfortable | compact
        "font_scale": 100,
        "sidebar": "left",  # left | right
        "layout_mode": "custom",  # custom | adaptive
        "cards": [],  # [{"id", "size", "hidden"}] — ordem do painel inicial
    },
    # Contagem de utilização das áreas da aplicação (para o modo adaptativo).
    "usage": {},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get_all_settings(db: Session) -> dict[str, Any]:
    stored = {s.key: s.value for s in db.scalars(select(Setting))}
    return _merge(DEFAULT_SETTINGS, stored)


def get_setting(db: Session, key: str) -> Any:
    return get_all_settings(db).get(key)


def put_setting(db: Session, key: str, value: Any) -> None:
    current = db.get(Setting, key)
    if current is None:
        db.add(Setting(key=key, value=value))
    else:
        current.value = value


# --------------------------------------------------------------------------- Fuso horário


def local_tz(db: Session) -> ZoneInfo:
    name = get_setting(db, "timezone") or "UTC"
    try:
        return ZoneInfo(str(name))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_today(db: Session) -> date:
    return datetime.now(local_tz(db)).date()


def day_bounds(db: Session, day: date, days: int = 1) -> tuple[datetime, datetime]:
    """Início e fim (exclusivo) de ``days`` dias locais, como datetimes com fuso."""
    tz = local_tz(db)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=days), time.min, tzinfo=tz)
    return start, end


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())
