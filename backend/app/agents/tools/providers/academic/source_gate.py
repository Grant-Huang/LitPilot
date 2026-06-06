"""Global per-source serialization for multi_academic (one in-flight call per source)."""
from __future__ import annotations

import asyncio

SOURCE_NAMES: tuple[str, ...] = (
    "openalex",
    "arxiv",
    "crossref",
    "pubmed",
    "semantic_scholar",
)

_locks: dict[str, asyncio.Lock] | None = None


def _locks_map() -> dict[str, asyncio.Lock]:
    global _locks
    if _locks is None:
        _locks = {name: asyncio.Lock() for name in SOURCE_NAMES}
    return _locks


def source_count() -> int:
    return len(SOURCE_NAMES)


class source_slot:
    """Async context manager: hold the sole slot for one academic search source."""

    def __init__(self, source: str) -> None:
        self.source = source
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> None:
        locks = _locks_map()
        if self.source not in locks:
            locks[self.source] = asyncio.Lock()
        self._lock = locks[self.source]
        await self._lock.acquire()

    async def __aexit__(self, *exc: object) -> None:
        if self._lock is not None:
            self._lock.release()


def reset_for_tests() -> None:
    global _locks
    _locks = None
