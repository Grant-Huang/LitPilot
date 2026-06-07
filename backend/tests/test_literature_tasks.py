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
async def test_create_task_persists_source_mode(tmp_path, monkeypatch):
    with patch(
        "app.tasks.literature_tasks.stream_literature_turn",
        side_effect=lambda *a, **k: _fake_turn(),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/tasks",
                json={
                    "message": "user only",
                    "literature_source_mode": "user_only",
                },
            )
            task_id = created.json()["data"]["task_id"]
            record = get_task_store().get_task(task_id)
            assert record is not None
            assert record.literature_source_mode == "user_only"


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
