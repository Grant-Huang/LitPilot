"""Retry helpers for web_search / web_fetch."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
    delay_ms: int = 500,
) -> T:
    """Run async fn up to (1 + max_retries) times."""
    last_err: Exception | None = None
    attempts = max(0, max_retries) + 1
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as e:
            last_err = e
            if attempt + 1 >= attempts:
                break
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
    assert last_err is not None
    raise last_err
