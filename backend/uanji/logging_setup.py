"""Logs estruturados (JSON por linha) com redacção de valores sensíveis."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SENSITIVE = re.compile(r"(?i)(token|secret|password|authorization|api[_-]?key)(\"?\s*[:=]\s*\"?)([^\s\",}]+)")
_GH_TOKEN = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9-]{20,})\b")


def redact(text: str) -> str:
    text = _SENSITIVE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return _GH_TOKEN.sub("[REDACTED]", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = json.loads(redact(json.dumps(extra, default=str)))
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(logs_dir: Path, level: str = "INFO") -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "backend.log"
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        if getattr(h, "_uanji", False):
            root.removeHandler(h)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    fh._uanji = True  # type: ignore[attr-defined]
    sh = logging.StreamHandler()
    sh.setFormatter(JsonFormatter())
    sh._uanji = True  # type: ignore[attr-defined]
    root.addHandler(fh)
    root.addHandler(sh)
    return log_file
