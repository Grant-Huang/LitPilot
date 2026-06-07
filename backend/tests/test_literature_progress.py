import asyncio
import time

import pytest

from app.agents.literature_progress import iter_progress_while_pending


@pytest.mark.asyncio
async def test_iter_progress_while_pending_emits_during_slow_task() -> None:
    async def slow() -> str:
        await asyncio.sleep(0.05)
        return "ok"

    task = asyncio.create_task(slow())
    ticks: list[tuple[str, dict]] = []
    async for ev in iter_progress_while_pending(
        "search",
        "test query",
        task,
        interval_sec=0.02,
    ):
        ticks.append(ev)
    assert await task == "ok"
    assert ticks
    assert ticks[0][0] == "literature_progress"
    assert ticks[0][1]["stage"] == "search"
    assert ticks[0][1]["detail"] == "test query"
    assert ticks[0][1]["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_merge_async_iter_with_progress_emits_during_slow_stream() -> None:
    from app.agents.literature_progress import merge_async_iter_with_progress

    async def slow_stream():
        await asyncio.sleep(0.05)
        yield ("think", {"delta": "hello"})

    ticks: list[tuple[str, dict]] = []
    items: list[tuple[str, dict]] = []
    async for ev in merge_async_iter_with_progress(
        slow_stream(),
        "understand",
        "planning",
        interval_sec=0.02,
    ):
        if ev[0] == "literature_progress":
            ticks.append(ev)
        else:
            items.append(ev)
    assert ticks
    assert ticks[0][1]["stage"] == "understand"
    assert items == [("think", {"delta": "hello"})]


@pytest.mark.asyncio
async def test_iter_progress_while_pending_fast_task_no_ticks() -> None:
    async def fast() -> int:
        return 1

    task = asyncio.create_task(fast())
    ticks = [ev async for ev in iter_progress_while_pending("fetch", "x", task, interval_sec=5.0)]
    assert await task == 1
    assert ticks == []
