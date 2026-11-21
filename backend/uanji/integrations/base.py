"""Contrato dos adaptadores de integrações externas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session


class IntegrationAdapter(ABC):
    provider: str
    label: str

    @abstractmethod
    def status(self, db: Session) -> dict[str, Any]:
        """Estado actual sem contactar o serviço externo."""

    @abstractmethod
    def configure(self, db: Session, secret_id: str | None) -> dict[str, Any]:
        """Associa (ou remove) a credencial guardada no cofre."""

    @abstractmethod
    def test(self, db: Session) -> dict[str, Any]:
        """Verifica a ligação junto do serviço externo."""


def registry() -> dict[str, IntegrationAdapter]:
    from .github import GitHubAdapter

    return {a.provider: a for a in [GitHubAdapter()]}
