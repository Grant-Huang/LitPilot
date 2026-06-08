"""Unit tests for file-backed and Turso-backed literature task store."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.tasks.task_store import FileTaskStore, TursoTaskStore


def test_file_task_store_create_claim_and_events(tmp_path: Path) -> None:
    store = FileTaskStore(root=tmp_path / "tasks")
    record = store.create_task(session_id="sess1", message="hello", fetch_urls=["https://a"])
    assert record.status == "pending"
    assert store.try_claim(record.id, "worker-a") is True
    claimed = store.get_task(record.id)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.worker_id == "worker-a"
    assert store.try_claim(record.id, "worker-b") is False

    count = store.append_event(record.id, 'data: {"type":"stage"}\n\n')
    assert count == 1
    events = store.list_events(record.id, since=0)
    assert len(events) == 1
    assert store.list_events(record.id, since=1) == []

    store.update_task(record.id, status="completed", progress=100, stage="completed")
    done = store.get_task(record.id)
    assert done is not None
    assert done.status == "completed"
    assert done.progress == 100
    assert store.list_active_tasks() == []


def test_file_task_store_cancel_pending(tmp_path: Path) -> None:
    store = FileTaskStore(root=tmp_path / "tasks")
    record = store.create_task(session_id="s", message="x")
    cancelled = store.request_cancel(record.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert store.is_cancel_requested(record.id) is True


def test_file_task_store_requeue_stale_running(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    store = FileTaskStore(root=tmp_path / "tasks")
    record = store.create_task(session_id="s", message="stale")
    assert store.try_claim(record.id, "worker-dead") is True

    stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    meta_path = store._meta_path(record.id)
    import json

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    meta["updated_at"] = stale_ts
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    cutoff = datetime.now(timezone.utc).timestamp() - 600
    requeued = store.requeue_stale_running(cutoff)
    assert record.id in requeued
    refreshed = store.get_task(record.id)
    assert refreshed is not None
    assert refreshed.status == "pending"
    assert refreshed.worker_id is None


# ---------------------------------------------------------------------------
# TursoTaskStore tests
# ---------------------------------------------------------------------------


def test_turso_task_store_append_events_batch_uses_executemany() -> None:
    """append_events_batch must call executemany on the connection.

    This test was added after a production bug where TursoHttpConnection had no
    executemany method, causing a silent AttributeError that dropped all batched
    events. The test verifies that TursoTaskStore delegates to executemany
    with correct SQL and parameters.
    """
    mock_conn = MagicMock()
    max_seq_result = MagicMock()
    max_seq_result.fetchone.return_value = (0,)
    mock_conn.execute.return_value = max_seq_result

    with patch("app.storage.turso_http.get_connection", return_value=mock_conn):
        with patch("app.storage.turso_db.apply_migrations"):
            store = TursoTaskStore()

    events = [
        'data: {"name":"session","version":"1.0","data":{"session_id":"s1"}}\n\n',
        'data: {"type":"capabilities"}\n\n',
    ]
    count = store.append_events_batch("task-1", events)

    assert mock_conn.executemany.called, (
        "TursoTaskStore.append_events_batch must delegate to "
        "self._conn.executemany for batch INSERT"
    )
    assert count == 2

    sql, rows = mock_conn.executemany.call_args[0]
    assert "INSERT INTO literature_task_events" in sql
    assert len(rows) == 2
    # Verify each row has the correct shape: (task_id, seq, event_line, created_at)
    assert rows[0][0] == "task-1"
    assert rows[0][1] == 1
    assert rows[0][2] == events[0].rstrip("\n")
    assert rows[1][0] == "task-1"
    assert rows[1][1] == 2
    assert rows[1][2] == events[1].rstrip("\n")


def test_turso_task_store_append_events_batch_empty() -> None:
    """append_events_batch with empty list returns 0 without calling the DB."""
    mock_conn = MagicMock()

    with patch("app.storage.turso_http.get_connection", return_value=mock_conn):
        with patch("app.storage.turso_db.apply_migrations"):
            store = TursoTaskStore()

    count = store.append_events_batch("task-1", [])
    assert count == 0
    mock_conn.execute.assert_not_called()
    mock_conn.executemany.assert_not_called()


def test_turso_task_store_append_event_delegates_to_batch() -> None:
    """append_event delegates to append_events_batch (and therefore executemany)."""
    mock_conn = MagicMock()
    max_seq_result = MagicMock()
    max_seq_result.fetchone.return_value = (0,)
    mock_conn.execute.return_value = max_seq_result

    with patch("app.storage.turso_http.get_connection", return_value=mock_conn):
        with patch("app.storage.turso_db.apply_migrations"):
            store = TursoTaskStore()

    count = store.append_event("task-2", 'data: {"type":"stage"}\n\n')
    assert count == 1
    mock_conn.executemany.assert_called_once()
    sql, rows = mock_conn.executemany.call_args[0]
    assert len(rows) == 1  # single event → single row batch

