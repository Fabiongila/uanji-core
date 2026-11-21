from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uanji.config import Settings
from uanji.main import create_app
from uanji.services.vault import MemoryStore

TOKEN = "test-token-123"


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        env="test",
        data_dir=data_dir,
        token=TOKEN,
        secret_backend="memory",
        scheduler_enabled=False,
        log_level="WARNING",
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir: Path):  # type: ignore[no-untyped-def]
    a = create_app(make_settings(data_dir), secret_store=MemoryStore())
    yield a
    a.state.database.dispose()


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as c:
        yield c


@pytest.fixture
def anon(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with TestClient(app) as c:
        yield c
