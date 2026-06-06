"""Unified fetch queue: user uploads + search hits with shared parallel pool."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.literature_source import hit_from_url
from app.agents.parallel_fetch import fetch_sources_parallel
from app.agents.url_list import canonical_url_keys, filter_hits_excluding_keys
from app.library.canonical import canonical_key, normalize_url


@dataclass
class FetchCoordinatorMetrics:
    user_urls_enqueued: int = 0
    search_hits_enqueued: int = 0
    duplicate_url_skipped: int = 0
    user_fetch_started_at: float | None = None
    search_ended_at: float | None = None
    user_fetch_done_before_search_end: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_urls_enqueued": self.user_urls_enqueued,
            "search_hits_enqueued": self.search_hits_enqueued,
            "duplicate_url_skipped": self.duplicate_url_skipped,
            "user_fetch_started_at": self.user_fetch_started_at,
            "search_ended_at": self.search_ended_at,
            "user_fetch_done_before_search_end": self.user_fetch_done_before_search_end,
        }


@dataclass
class FetchCoordinatorResult:
    results: list[tuple[dict[str, str], str, str | None]] = field(default_factory=list)
    metrics: FetchCoordinatorMetrics = field(default_factory=FetchCoordinatorMetrics)


class FetchCoordinator:
    """Priority fetch: upload URLs start immediately; search hits fill remaining budget."""

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
        fetch_cap: int,
        upload_urls: list[str] | None = None,
        corpus=None,
    ) -> None:
        self._fetch_api_key = fetch_api_key
        self._llm = llm
        self._parallel = parallel
        self._timeout_sec = timeout_sec
        self._fetch_retry_count = fetch_retry_count
        self._fetch_retry_delay_ms = fetch_retry_delay_ms
        self._fetch_provider = fetch_provider
        self._fetch_cap = max(0, int(fetch_cap))
        self._corpus = corpus
        self._upload_keys = canonical_url_keys(upload_urls or [])
        upload_n = len(upload_urls or [])
        self._upload_reserved = min(upload_n, self._fetch_cap) if upload_n else 0
        self._search_cap = max(0, self._fetch_cap - self._upload_reserved)
        self._seen: set[str] = set()
        self._upload_submitted = 0
        self._search_submitted = 0
        self._tasks: list[asyncio.Task] = []
        self._user_task: asyncio.Task | None = None
        self.metrics = FetchCoordinatorMetrics()
        self.results: list[tuple[dict[str, str], str, str | None]] = []

    def _key(self, url: str) -> str:
        return canonical_key(url=url) or normalize_url(url) or url

    def _enqueue_batch(self, hits: list[dict[str, str]], *, is_upload: bool) -> int:
        fresh: list[dict[str, str]] = []
        cap = self._upload_reserved if is_upload else self._search_cap
        submitted = self._upload_submitted if is_upload else self._search_submitted

        for hit in hits:
            url = str(hit.get("url") or "").strip()
            if not url or submitted >= cap:
                continue
            if self._corpus and self._corpus.has_url(url):
                continue
            key = self._key(url)
            if key in self._seen:
                continue
            self._seen.add(key)
            fresh.append(hit)
            submitted += 1
            if submitted >= cap:
                break

        if is_upload:
            self._upload_submitted = submitted
        else:
            self._search_submitted = submitted

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
                prioritize_upload=is_upload,
            )

        task = asyncio.create_task(_run(fresh))
        if is_upload:
            self._user_task = task
        self._tasks.append(task)
        return len(fresh)

    def start_user_urls(self, urls: list[str]) -> int:
        if not urls or self._upload_reserved <= 0:
            return 0
        hits = [hit_from_url(u) for u in urls]
        n = self._enqueue_batch(hits, is_upload=True)
        if n:
            self.metrics.user_urls_enqueued = n
            self.metrics.user_fetch_started_at = time.monotonic()
        return n

    def enqueue_search_hits(self, hits: list[dict[str, str]]) -> int:
        filtered, skipped = filter_hits_excluding_keys(hits, self._upload_keys)
        self.metrics.duplicate_url_skipped += skipped
        n = self._enqueue_batch(filtered, is_upload=False)
        if n:
            self.metrics.search_hits_enqueued += n
        return n

    def enqueue_pass_hits(self, hits: list[dict[str, str]]) -> int:
        """Backward-compatible alias for pipeline incremental enqueue."""
        return self.enqueue_search_hits(hits)

    def filter_search_hits_for_merge(self, hits: list[dict[str, str]]) -> list[dict[str, str]]:
        filtered, skipped = filter_hits_excluding_keys(hits, self._upload_keys)
        self.metrics.duplicate_url_skipped += skipped
        return filtered

    def mark_search_ended(self) -> None:
        self.metrics.search_ended_at = time.monotonic()
        if self._user_task is not None:
            self.metrics.user_fetch_done_before_search_end = self._user_task.done()

    async def finalize(self) -> FetchCoordinatorResult:
        if self._tasks:
            batches = await asyncio.gather(*self._tasks, return_exceptions=True)
            for batch in batches:
                if isinstance(batch, list):
                    self.results.extend(batch)

        if (
            self.metrics.user_fetch_started_at is not None
            and self.metrics.search_ended_at is not None
            and self._user_task is not None
            and self.metrics.user_fetch_done_before_search_end is None
        ):
            self.metrics.user_fetch_done_before_search_end = self._user_task.done()

        return FetchCoordinatorResult(results=self.results, metrics=self.metrics)


# Backward-compatible alias
PipelinedFetchCoordinator = FetchCoordinator
