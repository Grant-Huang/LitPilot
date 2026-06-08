"""Tests for background literature task registry and API."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tasks.literature_tasks import get_task_registry, reset_task_registry_for_tests
from app.tasks.task_store import FileTaskStore, get_task_store, reset_task_store_for_tests


async def _fake_turn(*_args, **_kwargs):
    yield ("stage", {"name": "文献检索", "state": "active"})
    await asyncio.sleep(0.05)
    yield ("stage", {"name": "文献检索", "state": "done"})
    yield (
        "literature_progress",
        {"stage": "search", "detail": "topic", "completed": 2, "total": 4},
    )
    yield ("stage", {"name": "完成", "state": "done"})


@pytest.fixture(autouse=True)
def _reset_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("LITPILOT_TASK_SWEEP_ENABLED", "0")
    task_root = tmp_path / "tasks"
    reset_task_store_for_tests(FileTaskStore(root=task_root))
    reset_task_registry_for_tests()
    yield
    reset_task_registry_for_tests()
    reset_task_store_for_tests(None)


@pytest.mark.asyncio
async def test_create_task_and_status():
    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=lambda *a, **k: _fake_turn(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/tasks",
                json={"message": "test review topic"},
            )
            assert created.status_code == 200
            body = created.json()
            assert body["status"] == "success"
            task_id = body["data"]["task_id"]
            session_id = body["data"]["session_id"]
            assert task_id
            assert session_id

            for _ in range(30):
                st = await client.get(f"/api/tasks/{task_id}/status")
                assert st.status_code == 200
                row = st.json()["data"]
                if row["status"] in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("task did not finish in time")

            assert row["status"] == "completed"
            assert row["progress"] == 100
            assert row["event_count"] > 0


@pytest.mark.asyncio
async def test_cancel_task():
    async def slow_turn(*_args, **_kwargs):
        yield ("stage", {"name": "文献检索", "state": "active"})
        await asyncio.sleep(2.0)
        yield ("stage", {"name": "完成", "state": "done"})

    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=lambda *a, **k: slow_turn(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/tasks", json={"message": "slow"})
            task_id = created.json()["data"]["task_id"]
            await asyncio.sleep(0.05)
            deleted = await client.delete(f"/api/tasks/{task_id}")
            assert deleted.status_code == 200
            assert deleted.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_list_active_tasks():
    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=lambda *a, **k: _fake_turn(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/tasks", json={"message": "x"})
            task_id = created.json()["data"]["task_id"]
            active = await client.get("/api/tasks/active")
            assert active.status_code == 200
            ids = [row["task_id"] for row in active.json()["data"]["items"]]
            assert task_id in ids

            for _ in range(30):
                row = (
                    await client.get(f"/api/tasks/{task_id}/status")
                ).json()["data"]
                if row["status"] == "completed":
                    break
                await asyncio.sleep(0.05)

            active2 = await client.get("/api/tasks/active")
            ids2 = [row["task_id"] for row in active2.json()["data"]["items"]]
            assert task_id not in ids2


@pytest.mark.asyncio
async def test_sweep_picks_up_pending_task():
    from app.tasks.task_store import get_task_store

    store = get_task_store()
    record = store.create_task(session_id="sess", message="orphan")
    assert record.status == "pending"

    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=lambda *a, **k: _fake_turn(),
    ):
        registry = get_task_registry()
        await registry.sweep_once()

        row = store.get_task(record.id)
        assert row is not None
        for _ in range(30):
            row = store.get_task(record.id)
            assert row is not None
            if row.status in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("sweeper did not pick up pending task")

        assert row.status == "completed"



@pytest.mark.asyncio
async def test_task_rerun_skips_duplicate_user_message(tmp_path, monkeypatch):
    from app.storage.file_store import FileStore

    data_root = tmp_path / "data"
    store = FileStore(data_root)
    monkeypatch.setattr("app.tasks.literature_tasks.get_store", lambda: store)

    session = store.create_session("idem")
    record = get_task_store().create_task(
        session_id=session["id"],
        message="once",
    )
    store.append_message(session["id"], "user", "once")

    calls: list[bool] = []

    async def tracked_turn(*_args, persist_user_message=True, **_kwargs):
        calls.append(persist_user_message)
        async for ev in _fake_turn():
            yield ev

    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=tracked_turn,
    ):
        registry = get_task_registry()
        await registry._run(record.id)

        for _ in range(30):
            row = get_task_store().get_task(record.id)
            assert row is not None
            if row.status == "completed":
                break
            await asyncio.sleep(0.05)

        msgs = store.load_messages(session["id"])
        assert sum(1 for m in msgs if m.get("role") == "user") == 1
        assert calls == [False]


@pytest.mark.asyncio
async def test_initial_events_written_before_turn_yields() -> None:
    """_run writes initial events (session, capabilities, stage) synchronously
    before entering the async for loop over stream_literature_turn.

    This is a regression test for a production bug where initial events went
    through _EventBatchBuffer → batch.flush() → TursoTaskStore.append_events_batch
    → self._conn.executemany(...), but TursoHttpConnection had no executemany
    method, causing a silent AttributeError that left event_count=0 forever.
    """
    store = get_task_store()
    record = store.create_task(session_id="sess-init", message="test init events")

    async def _blocking_turn(*_args, **_kwargs):
        # Block forever: this ensures _run never processes any turn events,
        # so only the synchronous initial events (written before async for)
        # end up in list_events.
        block = asyncio.Event()
        await block.wait()
        yield ("stage", {"name": "完成", "state": "done"})  # unreachable

    registry = get_task_registry()

    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=_blocking_turn,
    ):
        runner = asyncio.create_task(registry._run(record.id))
        # Yield to the event loop so _run executes up to its first await
        # (which is inside _blocking_turn). At that point initial events
        # must already be on disk.
        await asyncio.sleep(0.15)

        events = store.list_events(record.id, since=0)
        task = store.get_task(record.id)

        # Clean up: cancel the blocked runner
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass

    assert task is not None
    assert task.progress >= 2, (
        f"Task progress not updated after initial events: {task.progress}"
    )
    assert task.stage == "understanding", (
        f"Task stage not updated after init: {task.stage}"
    )
    assert len(events) >= 3, (
        f"Initial events not written before turn yields: "
        f"expected >= 3 (session, capabilities, stage), got {len(events)}"
    )

    # Verify individual event types are present
    assert any("session" in e for e in events), (
        f"Missing session event. Events: {events[:3]}"
    )
    assert any("capabilities" in e for e in events), (
        f"Missing capabilities event. Events: {events[:3]}"
    )
    assert any('"理解研究问题"' in e or '"stage"' in e for e in events), (
        f"Missing stage event. Events: {events[:3]}"
    )
