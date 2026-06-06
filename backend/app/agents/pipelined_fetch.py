"""Background fetch tasks while multi-pass search continues."""
from __future__ import annotations

import asyncio
from typing import Any

from app.agents.parallel_fetch import fetch_sources_parallel
from app.library.canonical import canonical_key, normalize_url


class PipelinedFetchCoordinator:
    """Enqueue search-pass hits; fetch in parallel while search continues."""

    def __init__(
        self,
        *,
        fetch_api_key: str | None,
        llm: Any,
        parallel: int,
        timeout_sec: float,
        fetch_retry_count: int,
        fetch_retry_delay_ms: int,
        fetch_provider: str | None,
        max_urls: int,
        corpus=None,
    ) -> None:
        self._fetch_api_key = fetch_api_key
        self._llm = llm
        self._parallel = parallel
        self._timeout_sec = timeout_sec
        self._fetch_retry_count = fetch_retry_count
        self._fetch_retry_delay_ms = fetch_retry_delay_ms
        self._fetch_provider = fetch_provider
        self._max_urls = max_urls
        self._corpus = corpus
        self._seen: set[str] = set()
        self._submitted = 0
        self._tasks: list[asyncio.Task] = []
        self.results: list[tuple[dict[str, str], str, str | None]] = []

    def _key(self, url: str) -> str:
        return canonical_key(url=url) or normalize_url(url) or url

    def enqueue_pass_hits(self, hits: list[dict[str, str]]) -> int:
        fresh: list[dict[str, str]] = []
        for hit in hits:
            url = str(hit.get("url") or "").strip()
            if not url or self._submitted >= self._max_urls:
                continue
            if self._corpus and self._corpus.has_url(url):
                continue
            key = self._key(url)
            if key in self._seen:
                continue
            self._seen.add(key)
            fresh.append(hit)
            self._submitted += 1
            if self._submitted >= self._max_urls:
                break
        if not fresh:
            return 0

        async def _run(batch: list[dict[str, str]]) -> list:
            return await fetch_sources_parallel(
                batch,
                api_key=self._fetch_api_key,
                llm=self._llm,
                parallel=self._parallel,
                timeout_per_url=self._timeout_sec,
                max_urls=len(batch),
                retry_count=self._fetch_retry_count,
                retry_delay_ms=self._fetch_retry_delay_ms,
                fetch_provider=self._fetch_provider,
            )

        self._tasks.append(asyncio.create_task(_run(fresh)))
        return len(fresh)

    async def finalize(self) -> list[tuple[dict[str, str], str, str | None]]:
        if self._tasks:
            batches = await asyncio.gather(*self._tasks, return_exceptions=True)
            for batch in batches:
                if isinstance(batch, list):
                    self.results.extend(batch)
        return self.results
