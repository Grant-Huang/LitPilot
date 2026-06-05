"""Unit tests for TursoStore with mocked HTTP pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.storage.backend import reset_store_for_tests
from app.storage.turso_repo import TursoRepo
from app.storage.turso_store import TursoStore


def _pipeline_ok(rows: list | None = None, affected: int = 0) -> dict:
    result = {
        "cols": [],
        "rows": rows or [],
        "affected_row_count": affected,
        "last_insert_rowid": None,
    }
    return {
        "baton": None,
        "base_url": None,
        "results": [
            {
                "type": "ok",
                "response": {"type": "execute", "result": result},
            },
            {"type": "ok", "response": {"type": "close"}},
        ],
    }


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.execute.return_value = MagicMock(fetchall=lambda: [], fetchone=None)
    return conn


@pytest.fixture
def turso_store(tmp_path: Path, mock_conn: MagicMock) -> TursoStore:
    reset_store_for_tests()
    mock_repo = MagicMock(spec=TursoRepo)
    mock_repo.conn = mock_conn
    with (
        patch("app.storage.turso_store.apply_migrations"),
        patch("app.storage.turso_store.TursoRepo", return_value=mock_repo),
    ):
        store = TursoStore(root=tmp_path)
    store._repo = TursoRepo(conn=mock_conn)
    return store


def test_create_session_calls_insert(turso_store: TursoStore, mock_conn: MagicMock) -> None:
    mock_conn.execute.return_value = MagicMock(fetchall=lambda: [], fetchone=None)
    meta = turso_store.create_session("测试会话")
    assert meta["title"] == "测试会话"
    assert meta["id"]
    assert mock_conn.execute.called


def test_config_list_roundtrip(turso_store: TursoStore, mock_conn: MagicMock) -> None:
    saved: dict[str, object] = {}

    def fake_execute(sql, params=()):
        sql_s = str(sql)
        if "INSERT INTO config_documents" in sql_s and params:
            saved["raw"] = json.loads(params[1])
        return MagicMock(fetchall=lambda: [], fetchone=None)

    mock_conn.execute.side_effect = fake_execute
    turso_store._save_config_list(
        turso_store.system_credentials_path,
        [{"id": "c1", "type": "tavily", "name": "Tavily"}],
    )
    assert saved.get("raw")

    def fake_load(sql, params=()):
        if "SELECT content_json FROM config_documents" in str(sql):
            return MagicMock(
                fetchone=lambda: (json.dumps(saved["raw"], ensure_ascii=False),)
            )
        return MagicMock(fetchall=lambda: [], fetchone=None)

    mock_conn.execute.side_effect = fake_load
    items = turso_store._load_config_list(turso_store.system_credentials_path)
    assert items[0]["id"] == "c1"


def test_get_store_uses_turso_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reset_store_for_tests()
    monkeypatch.setenv("LITPILOT_STORAGE_BACKEND", "turso")
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://test.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "token")
    with (
        patch("app.storage.turso_store.apply_migrations"),
        patch("app.storage.turso_repo.get_connection"),
    ):
        from app.storage.backend import get_store

        store = get_store()
    assert isinstance(store, TursoStore)
    reset_store_for_tests()
