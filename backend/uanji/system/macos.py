"""Acções no macOS pedidas ao assistente.

Todas passam pelas ferramentas tipadas (``assistant/tools.py``) com nível de risco:
- abrir aplicações, sites e pastas, volume, estado do sistema: risco «sistema» (sem perda de dados);
- fechar aplicações: altera o estado (pode haver trabalho por guardar) → confirmação;
- comandos de terminal: desligados por omissão; quando ligados, pedem SEMPRE confirmação,
  mostram o comando exacto, correm com tempo limite e nunca com ``sudo``.

Os processos externos são lançados através de ``runner`` (substituível nos testes).
"""

from __future__ import annotations

import re
import shutil
import subprocess  # noqa: S404 (lista de argumentos; o terminal só por pedido confirmado)
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse


@dataclass
class RunResult:
    code: int
    stdout: str
    stderr: str


def _default_runner(args: list[str], timeout: float = 10.0, cwd: str | None = None) -> RunResult:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=cwd, check=False)  # noqa: S603
    return RunResult(p.returncode, p.stdout, p.stderr)


runner: Callable[..., RunResult] = _default_runner

APP_DIRS = [
    Path("/Applications"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path("/Applications/Utilities"),
    Path.home() / "Applications",
]
# Nomes comuns ditos em voz alta → nome da aplicação.
ALIASES = {
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "chrome": "Google Chrome",
    "google": "Google Chrome",
    "terminal": "Terminal",
    "notas": "Notes",
    "calendario": "Calendar",
    "mail": "Mail",
    "correio": "Mail",
    "definicoes": "System Settings",
    "definicoes do sistema": "System Settings",
    "musica": "Music",
    "whatsapp": "WhatsApp",
}


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def installed_apps() -> list[Path]:
    apps: list[Path] = []
    for d in APP_DIRS:
        if d.is_dir():
            apps += [p for p in d.iterdir() if p.suffix == ".app"]
    return apps


def find_app(name: str) -> Path | None:
    want = _norm(ALIASES.get(_norm(name), name))
    apps = installed_apps()
    exact = [a for a in apps if _norm(a.stem) == want]
    if exact:
        return exact[0]
    starts = [a for a in apps if _norm(a.stem).startswith(want) or want in _norm(a.stem).split()]
    return starts[0] if len(starts) == 1 else None


def open_app(name: str) -> str:
    app = find_app(name)
    if app is None:
        raise LookupError(f"Não encontrei a aplicação «{name}» em /Applications.")
    r = runner(["/usr/bin/open", "-a", str(app)])
    if r.code != 0:
        raise RuntimeError(r.stderr.strip() or f"Não foi possível abrir {app.stem}.")
    return app.stem


def running_apps() -> list[dict[str, Any]]:
    try:
        import AppKit  # type: ignore[import-untyped,import-not-found,unused-ignore]
    except Exception:
        return []
    ws = AppKit.NSWorkspace.sharedWorkspace()
    return [
        {
            "name": str(a.localizedName()),
            "bundle_id": str(a.bundleIdentifier() or ""),
            "pid": int(a.processIdentifier()),
        }
        for a in ws.runningApplications()
        if a.activationPolicy() == 0  # aplicações normais (com ícone na Dock)
    ]


def quit_app(name: str) -> str:
    """Pede à aplicação que termine (como ⌘Q: a aplicação pode perguntar se quer guardar)."""
    try:
        import AppKit
    except Exception as e:
        raise RuntimeError("Indisponível neste sistema.") from e
    want = _norm(ALIASES.get(_norm(name), name))
    ws = AppKit.NSWorkspace.sharedWorkspace()
    matches = [
        a
        for a in ws.runningApplications()
        if a.activationPolicy() == 0
        and (_norm(str(a.localizedName())) == want or _norm(str(a.localizedName())).startswith(want))
    ]
    if not matches:
        raise LookupError(f"A aplicação «{name}» não está aberta.")
    if "uanji" in _norm(str(matches[0].localizedName())):
        raise RuntimeError("Não posso fechar o próprio UANJI CORE.")
    matches[0].terminate()
    return str(matches[0].localizedName())


def open_url(target: str) -> str:
    """Abre um endereço http(s) ou pesquisa o texto no motor de pesquisa."""
    t = target.strip()
    if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", t):
        t = "https://" + t
    if urlparse(t).scheme not in ("http", "https"):
        t = "https://www.google.com/search?q=" + quote_plus(target.strip())
    r = runner(["/usr/bin/open", t])
    if r.code != 0:
        raise RuntimeError("Não foi possível abrir o endereço.")
    return t


def open_path(path: str) -> str:
    p = Path(path).expanduser().resolve()
    home = Path.home().resolve()
    if not p.exists():
        raise LookupError(f"O caminho {p} não existe.")
    if not p.is_relative_to(home) and not str(p).startswith("/Applications"):
        raise PermissionError("Só abro pastas e ficheiros dentro da sua pasta pessoal.")
    r = runner(["/usr/bin/open", str(p)])
    if r.code != 0:
        raise RuntimeError("Não foi possível abrir o caminho.")
    return str(p)


def set_volume(level: int) -> int:
    level = max(0, min(100, int(level)))
    r = runner(["/usr/bin/osascript", "-e", f"set volume output volume {level}"])
    if r.code != 0:
        raise RuntimeError("Não foi possível ajustar o volume.")
    return level


def system_status() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        batt = runner(["/usr/bin/pmset", "-g", "batt"]).stdout
        m = re.search(r"(\d+)%;\s*([^;]+);", batt)
        if m:
            out["battery_percent"] = int(m.group(1))
            out["battery_state"] = m.group(2).strip()
        out["power_source"] = "corrente" if "AC Power" in batt else ("bateria" if "Battery Power" in batt else "")
    except (OSError, subprocess.SubprocessError):
        pass
    usage = shutil.disk_usage(Path.home())
    out["disk_free_gb"] = round(usage.free / 1e9, 1)
    out["disk_total_gb"] = round(usage.total / 1e9, 1)
    try:
        up = runner(["/usr/bin/uptime"]).stdout
        m2 = re.search(r"load averages?: ([\d.,]+)", up)
        if m2:
            out["load"] = m2.group(1).split()[0].replace(",", ".")
    except (OSError, subprocess.SubprocessError):
        pass
    out["running_apps"] = len(running_apps())
    return out


def status_sentence(s: dict[str, Any]) -> str:
    parts = []
    if "battery_percent" in s:
        state = {
            "charging": "a carregar",
            "discharging": "a descarregar",
            "charged": "carregada",
            "finishing charge": "quase carregada",
            "ac attached": "ligada à corrente",
        }.get(str(s.get("battery_state", "")).lower(), "")
        parts.append(f"bateria a {s['battery_percent']}%" + (f", {state}" if state else ""))
    parts.append(f"{s['disk_free_gb']} GB livres em disco")
    if s.get("running_apps"):
        parts.append(f"{s['running_apps']} aplicações abertas")
    return "Estado do Mac: " + ", ".join(parts) + "."


# --------------------------------------------------------------------------- Terminal

FORBIDDEN = [
    (r"(^|[;&|\s])sudo\b", "comandos com sudo não são permitidos"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)", "apagar a raiz ou a pasta pessoal não é permitido"),
    (r"\bmkfs|\bdiskutil\s+(erase|zero)|\bdd\s+if=", "operações de disco não são permitidas"),
    (r":\(\)\s*\{", "bomba de processos não é permitida"),
    (r"\bshutdown\b|\breboot\b|\bhalt\b", "desligar/reiniciar não é permitido por comando"),
]
MAX_OUTPUT = 4000


def check_command(command: str) -> None:
    c = command.strip()
    if not c:
        raise ValueError("Comando vazio.")
    for pattern, reason in FORBIDDEN:
        if re.search(pattern, c):
            raise PermissionError(f"Recusado: {reason}.")


def run_shell(command: str, timeout: float = 30.0) -> dict[str, Any]:
    """Executa um comando do utilizador em zsh, na pasta pessoal, com tempo limite."""
    check_command(command)
    try:
        r = runner(["/bin/zsh", "-c", command], timeout=timeout, cwd=str(Path.home()))
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"O comando excedeu {int(timeout)} s e foi interrompido.") from e
    out = (r.stdout or "")[-MAX_OUTPUT:]
    err = (r.stderr or "")[-1500:]
    return {
        "command": command,
        "exit_code": r.code,
        "stdout": out,
        "stderr": err,
        "argv0": command.split()[0] if command.strip() else "",
    }
