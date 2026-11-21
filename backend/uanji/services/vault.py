"""Cofre de segredos.

Os valores são guardados exclusivamente no macOS Keychain (via ``keyring``). A base de
dados guarda apenas metadados (nome, serviço, últimos 4 caracteres). O backend em
memória existe só para testes e é identificado como inseguro.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ConfirmationRequired, ServiceUnavailable, ValidationFailed
from ..models import Integration, SecretEntry, utcnow
from .common import get_or_404, log_activity

log = logging.getLogger(__name__)


class SecretStore(Protocol):
    name: str
    secure: bool

    def status(self) -> dict[str, object]: ...
    def set(self, key: str, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def delete(self, key: str) -> None: ...


class KeychainStore:
    name = "macos-keychain"
    secure = True

    def __init__(self, service: str) -> None:
        self.service = service

    def _backend(self) -> Any:
        import keyring

        return keyring.get_keyring()

    def status(self) -> dict[str, object]:
        try:
            backend = self._backend()
            backend_name = f"{type(backend).__module__}.{type(backend).__name__}"
            ok = "macOS" in backend_name or "OS_X" in backend_name
            return {
                "backend": backend_name,
                "available": ok,
                "secure": ok,
                "message": "Segredos protegidos pelo macOS Keychain."
                if ok
                else "O Keychain do macOS não está disponível; o cofre está desactivado.",
            }
        except Exception as e:  # pragma: no cover - depende do sistema
            return {"backend": "unknown", "available": False, "secure": False, "message": str(e)}

    def _require(self) -> None:
        if not self.status()["available"]:
            raise ServiceUnavailable("O macOS Keychain não está acessível. O segredo não foi guardado.")

    def set(self, key: str, value: str) -> None:
        self._require()
        self._backend().set_password(self.service, key, value)

    def get(self, key: str) -> str | None:
        self._require()
        value = self._backend().get_password(self.service, key)
        return value if value is None else str(value)

    def delete(self, key: str) -> None:
        self._require()
        import keyring.errors

        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            self._backend().delete_password(self.service, key)


class MemoryStore:
    """APENAS PARA TESTES. Não persiste e não protege os valores."""

    name = "memory-insecure"
    secure = False

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def status(self) -> dict[str, object]:
        return {
            "backend": self.name,
            "available": True,
            "secure": False,
            "message": "Cofre em memória (testes). NÃO é seguro para produção.",
        }

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


_store: SecretStore | None = None


def init_store(store: SecretStore) -> None:
    global _store
    _store = store


def store() -> SecretStore:
    if _store is None:
        raise RuntimeError("Cofre não inicializado")
    return _store


def _hint(value: str) -> str:
    return "…" + value[-4:] if len(value) >= 8 else "…"


def list_entries(db: Session) -> list[SecretEntry]:
    return list(db.scalars(select(SecretEntry).order_by(SecretEntry.service, SecretEntry.name)))


def create_entry(db: Session, name: str, service: str, description: str, value: str) -> SecretEntry:
    if not value:
        raise ValidationFailed("O valor do segredo não pode estar vazio.")
    e = SecretEntry(name=name, service=service, description=description, hint=_hint(value))
    db.add(e)
    db.flush()
    store().set(e.id, value)  # se falhar, a transacção é revertida
    log_activity(db, "secret", e.id, "created", f"Segredo criado: {name} ({service or 'geral'})", sensitive=True)
    return e


def update_entry(
    db: Session, entry_id: str, *, name: str | None, service: str | None, description: str | None, value: str | None
) -> SecretEntry:
    e = get_or_404(db, SecretEntry, entry_id)
    if name is not None:
        e.name = name
    if service is not None:
        e.service = service
    if description is not None:
        e.description = description
    if value:
        store().set(e.id, value)
        e.hint = _hint(value)
        log_activity(db, "secret", e.id, "rotated", f"Valor do segredo substituído: {e.name}", sensitive=True)
    return e


def reveal(db: Session, entry_id: str) -> str:
    """Devolve o valor. Só deve ser chamado mediante acção explícita do utilizador."""
    e = get_or_404(db, SecretEntry, entry_id)
    value = store().get(e.id)
    if value is None:
        raise ValidationFailed("O valor não foi encontrado no Keychain (pode ter sido removido externamente).")
    e.last_accessed_at = utcnow()
    log_activity(db, "secret", e.id, "revealed", f"Segredo copiado: {e.name}", sensitive=True)
    return value


def read_for_integration(db: Session, entry_id: str) -> str | None:
    """Leitura interna (ex.: token GitHub). Não regista o valor."""
    e = db.get(SecretEntry, entry_id)
    if e is None:
        return None
    return store().get(e.id)


def delete_entry(db: Session, entry_id: str, confirm: bool) -> None:
    e = get_or_404(db, SecretEntry, entry_id)
    used_by = list(db.scalars(select(Integration.provider).where(Integration.secret_id == e.id)))
    if not confirm:
        raise ConfirmationRequired(
            "Eliminar o segredo remove-o do Keychain. Confirme a operação.", {"used_by": used_by}
        )
    store().delete(e.id)
    log_activity(db, "secret", e.id, "deleted", f"Segredo eliminado: {e.name}", sensitive=True)
    db.delete(e)
