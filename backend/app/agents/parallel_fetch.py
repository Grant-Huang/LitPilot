from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.agents.content_pipeline import process_url_for_context
from app.agents.retry_utils import retry_async


async def _fetch_one_hit(
    hit: dict[str, str],
    *,
    api_key: str | None,
    llm: Any,
    timeout_per_url: float,
    retry_count: int,
    retry_delay_ms: int,
    fetch_provider: str | None,
    sem: asyncio.Semaphore,
) -> tuple[dict[str, str], str, str | None]:
    url = hit["url"]

    async def attempt() -> tuple[str, str | None]:
        return await asyncio.wait_for(
            process_url_for_context(
                url,
                api_key=api_key,
                llm=llm,
                fetch_timeout=timeout_per_url,
                title=hit.get("title") or "",
                fetch_provider=fetch_provider,
            ),
            timeout=timeout_per_url + 30,
        )

    async with sem:
        try:
            md, err = await retry_async(
                attempt,
                max_retries=retry_count,
                delay_ms=retry_delay_ms,
            )
            if err and retry_count:
                err = f"{err}（已重试 {retry_count} 次）"
            return hit, md, err
        except asyncio.TimeoutError:
            msg = "timeout"
            if retry_count:
                msg = f"{msg}（已重试 {retry_count} 次）"
            return hit, "", msg
        except Exception as e:
            msg = str(e)
            if retry_count:
                msg = f"{msg}（已重试 {retry_count} 次）"
            return hit, "", msg


async def iter_fetch_sources_parallel(
    hits: list[dict[str, str]],
    *,
    api_key: str | None,
    llm: Any,
    parallel: int,
    timeout_per_url: float,
    max_urls: int,
    retry_count: int = 0,
    retry_delay_ms: int = 500,
    fetch_provider: str | None = None,
) -> AsyncIterator[tuple[dict[str, str], str, str | None]]:
    """每完成一篇即 yield，顺序为完成先后（便于 SSE 逐条展示）。"""
    sem = asyncio.Semaphore(max(1, parallel))
    subset = hits[:max_urls]

    tasks = [
        asyncio.create_task(
            _fetch_one_hit(
                h,
                api_key=api_key,
                llm=llm,
                timeout_per_url=timeout_per_url,
                retry_count=retry_count,
                retry_delay_ms=retry_delay_ms,
                fetch_provider=fetch_provider,
                sem=sem,
            )
        )
        for h in subset
    ]
    try:
        for finished in asyncio.as_completed(tasks):
            yield await finished
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def iter_fetch_hits_stream(
    hits: AsyncIterator[dict[str, str]],
    *,
    api_key: str | None,
    llm: Any,
    parallel: int,
    timeout_per_url: float,
    max_urls: int,
    retry_count: int = 0,
    retry_delay_ms: int = 500,
    fetch_provider: str | None = None,
) -> AsyncIterator[tuple[dict[str, str], str, str | None]]:
    """Fetch hits as they arrive from an async iterator (search→fetch pipeline)."""
    sem = asyncio.Semaphore(max(1, parallel))
    pending: set[asyncio.Task] = set()
    submitted = 0

    async def drain_one() -> tuple[dict[str, str], str, str | None] | None:
        if not pending:
            return None
        done, still = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        pending.clear()
        pending.update(still)
        task = next(iter(done))
        return task.result()

    async for hit in hits:
        if submitted >= max_urls:
            break
        pending.add(
            asyncio.create_task(
                _fetch_one_hit(
                    hit,
                    api_key=api_key,
                    llm=llm,
                    timeout_per_url=timeout_per_url,
                    retry_count=retry_count,
                    retry_delay_ms=retry_delay_ms,
                    fetch_provider=fetch_provider,
                    sem=sem,
                )
            )
        )
        submitted += 1
        while len(pending) >= parallel:
            item = await drain_one()
            if item is not None:
                yield item

    while pending:
        item = await drain_one()
        if item is not None:
            yield item


async def fetch_sources_parallel(
    hits: list[dict[str, str]],
    *,
    api_key: str | None,
    llm: Any,
    parallel: int,
    timeout_per_url: float,
    max_urls: int,
    retry_count: int = 0,
    retry_delay_ms: int = 500,
    fetch_provider: str | None = None,
) -> list[tuple[dict[str, str], str, str | None]]:
    return [
        item
        async for item in iter_fetch_sources_parallel(
            hits,
            api_key=api_key,
            llm=llm,
            parallel=parallel,
            timeout_per_url=timeout_per_url,
            max_urls=max_urls,
            retry_count=retry_count,
            retry_delay_ms=retry_delay_ms,
            fetch_provider=fetch_provider,
        )
    ]
