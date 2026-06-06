"""Unit tests for file-backed literature task store."""
from __future__ import annotations

from pathlib import Path

from app.tasks.task_store import FileTaskStore


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

