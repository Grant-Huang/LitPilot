from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.file_store import FileStore
from app.storage.storage_settings import (
    build_storage_status,
    resolve_turso_credentials,
    set_runtime_turso_credentials,
    clear_runtime_turso_credentials,
)


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


def test_resolve_turso_credentials_prefers_runtime(
    monkeypatch,
) -> None:
    clear_runtime_turso_credentials()
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://env.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "env-token")
    set_runtime_turso_credentials("libsql://runtime.turso.io", "runtime-token")
    url, token = resolve_turso_credentials()
    assert url == "libsql://runtime.turso.io"
    assert token == "runtime-token"
    clear_runtime_turso_credentials()


def test_build_storage_status_file_backend(
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITPILOT_STORAGE_BACKEND", "file")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    status = build_storage_status(store)
    assert status["backend"] == "file"
    assert status["turso_ready"] is False
