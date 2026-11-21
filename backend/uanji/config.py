"""Configuração por ambiente.

Todas as variáveis usam o prefixo ``UANJI_``. Em produção, o processo desktop (Tauri)
define ``UANJI_DATA_DIR``, ``UANJI_PORT`` e ``UANJI_TOKEN`` ao lançar o backend.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


def _default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "com.uanji.core"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UANJI_", env_file=None, extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    data_dir: Path = Field(default_factory=_default_data_dir)
    host: str = "127.0.0.1"
    port: int = 8765
    # Token partilhado entre o processo desktop e o backend. Se não for definido,
    # é gerado aleatoriamente (o backend fica inacessível sem o conhecer).
    token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    # Origens autorizadas a fazer pedidos (Tauri + Vite em desenvolvimento).
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "tauri://localhost",
            "http://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ]
    )
    # Backend de segredos: "keychain" (macOS Keychain via keyring) ou "memory" (apenas testes).
    secret_backend: Literal["keychain", "memory"] = "keychain"  # noqa: S105
    keychain_service: str = "com.uanji.core"
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 60
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "uanji.db"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.backups_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
