"""Unit tests for TursoHttpConnection — specifically executemany and pipeline encoding."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.storage.turso_http import TursoHttpConnection, _encode_arg


def _pipeline_response(rows: list[list] | None = None, affected: int = 0) -> dict:
    """Build a standard Turso pipeline JSON response."""
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


class FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200) -> None:
        self._json = json_data
        self.status_code = status_code

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_executemany_exists() -> None:
    """Sanity: TursoHttpConnection has executemany method.

    This test was added after a production bug where TursoTaskStore.append_events_batch
    called self._conn.executemany(...) but TursoHttpConnection had no such method,
    causing a silent AttributeError that dropped all batched events.
    """
    conn = TursoHttpConnection("https://test.turso.io", "fake-token")
    assert hasattr(conn, "executemany")
    assert callable(conn.executemany)


def test_executemany_empty_parameters() -> None:
    """executemany with empty sequence returns an empty cursor without HTTP request."""
    conn = TursoHttpConnection("https://test.turso.io", "fake-token")
    result = conn.executemany("INSERT INTO t VALUES (?)", [])
    assert result.fetchall() == []
    assert result.fetchone() is None


def test_executemany_pipeline_encoding() -> None:
    """executemany sends each parameter row as a separate execute stmt in one pipeline."""
    captured_payloads: list[dict] = []

    def fake_post(url, *, headers, json):  # noqa: A002
        captured_payloads.append(json)
        return FakeResponse(_pipeline_response(affected=3))

    conn = TursoHttpConnection("https://test.turso.io", "fake-token")
    with patch.object(conn._client, "post", side_effect=fake_post):
        result = conn.executemany(
            "INSERT INTO events (task_id, seq, line) VALUES (?, ?, ?)",
            [
                ("task-1", 1, "data: hello\\n\\n"),
                ("task-1", 2, 'data: {"type":"stage"}\\n\\n'),
                ("task-1", 3, "data: done\\n\\n"),
            ],
        )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    requests = payload["requests"]
    # 3 execute stmts + 1 close = 4
    assert len(requests) == 4
    assert requests[-1]["type"] == "close"

    # Each execute carries the SQL and args
    assert requests[0]["stmt"]["sql"] == "INSERT INTO events (task_id, seq, line) VALUES (?, ?, ?)"
    assert requests[0]["stmt"]["args"] == [
        {"type": "text", "value": "task-1"},
        {"type": "integer", "value": "1"},
        {"type": "text", "value": "data: hello\\n\\n"},
    ]
    assert requests[1]["stmt"]["args"][0] == {"type": "text", "value": "task-1"}
    assert requests[1]["stmt"]["args"][1] == {"type": "integer", "value": "2"}


def test_executemany_single_row() -> None:
    """executemany with one parameter row still uses pipeline format."""
    captured: dict | None = None

    def fake_post(url, *, headers, json):  # noqa: A002
        nonlocal captured
        captured = json
        return FakeResponse(_pipeline_response(affected=1))

    conn = TursoHttpConnection("https://test.turso.io", "fake-token")
    with patch.object(conn._client, "post", side_effect=fake_post):
        conn.executemany("INSERT INTO t (a) VALUES (?)", [("x",)])

    assert captured is not None
    requests = captured["requests"]
    assert len(requests) == 2  # 1 execute + 1 close
    assert requests[0]["type"] == "execute"


def test_executemany_encodes_various_types() -> None:
    """executemany encodes null, int, float, text parameters correctly."""
    captured: dict | None = None

    def fake_post(url, *, headers, json):  # noqa: A002
        nonlocal captured
        captured = json
        return FakeResponse(_pipeline_response(affected=1))

    conn = TursoHttpConnection("https://test.turso.io", "fake-token")
    with patch.object(conn._client, "post", side_effect=fake_post):
        conn.executemany(
            "INSERT INTO t (a, b, c, d, e) VALUES (?, ?, ?, ?, ?)",
            [(None, True, 42, 3.14, "hello")],
        )

    args = captured["requests"][0]["stmt"]["args"]
    assert args[0] == {"type": "null"}
    assert args[1] == {"type": "integer", "value": "1"}  # True→1
    assert args[2] == {"type": "integer", "value": "42"}
    assert args[3] == {"type": "float", "value": "3.14"}
    assert args[4] == {"type": "text", "value": "hello"}
