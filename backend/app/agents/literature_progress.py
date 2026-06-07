"""Lightweight SSE progress ticks for long-running literature phases."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")

PROGRESS_INTERVAL_SEC = 5.0


def literature_progress_payload(
    stage: str,
    detail: str = "",
    *,
    elapsed_ms: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stage": stage,
        "detail": detail,
        "elapsed_ms": elapsed_ms,
    }
    body.update(extra)
    return body


async def iter_progress_while_pending(
    stage: str,
    detail: str,
    task: asyncio.Task[T],
    *,
    interval_sec: float = PROGRESS_INTERVAL_SEC,
    **metadata: Any,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Emit ``literature_progress`` every *interval_sec* while *task* runs."""
    started = time.monotonic()
    while not task.done():
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=interval_sec)
            break
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            yield (
                "literature_progress",
                literature_progress_payload(
                    stage,
                    detail,
                    elapsed_ms=elapsed_ms,
                    **metadata,
                ),
            )


async def merge_async_iter_with_progress(
    source: AsyncIterator[tuple[str, dict[str, Any]]],
    stage: str,
    detail: str,
    *,
    interval_sec: float = PROGRESS_INTERVAL_SEC,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield *source* items; emit ``literature_progress`` when idle longer than *interval_sec*."""
    started = time.monotonic()
    it = source.__aiter__()
    pending: asyncio.Task[tuple[str, dict[str, Any]]] | None = None

    async def pull_next() -> tuple[str, dict[str, Any]]:
        return await it.__anext__()

    while True:
        if pending is None:
            pending = asyncio.create_task(pull_next())
        done, _ = await asyncio.wait({pending}, timeout=interval_sec)
        if not done:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            yield (
                "literature_progress",
                literature_progress_payload(stage, detail, elapsed_ms=elapsed_ms),
            )
            continue
        try:
            item = pending.result()
            pending = None
            yield item
        except StopAsyncIteration:
            pending = None
            break
    if pending is not None and not pending.done():
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def run_with_progress_ticks(
    stage: str,
    detail: str,
    factory: Callable[[], Awaitable[T]],
    *,
    interval_sec: float = PROGRESS_INTERVAL_SEC,
    **metadata: Any,
) -> AsyncIterator[tuple[str, dict[str, Any]] | T]:
    """Yield progress ticks, then the awaitable result (sentinel ``("__result__", value)``)."""
    task = asyncio.create_task(factory())
    try:
        async for tick in iter_progress_while_pending(
            stage,
            detail,
            task,
            interval_sec=interval_sec,
            **metadata,
        ):
            yield tick
        yield ("__result__", await task)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
