"""Process-wide pacing and 429 backoff for external academic APIs."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

_locks: dict[str, asyncio.Lock] = {}
_last_request_at: dict[str, float] = {}

# arXiv: ~1 req / 3s; NCBI E-utilities: ~3 req/s without API key
INTERVALS: dict[str, float] = {
    "arxiv": 3.0,
    "ncbi": 0.34,
}

BACKOFF_INITIAL_SEC = 5.0
BACKOFF_MAX_SEC = 60.0
BACKOFF_JITTER_RATIO = 0.2
BACKOFF_BUDGET_SEC = 30.0


class BackoffBudgetExhausted(Exception):
    """Raised when cumulative 429 backoff exceeds the per-request budget."""


@dataclass
class BackoffBudget:
    """Cap total sleep time spent on 429 retries for one search call."""

    max_total_sec: float = BACKOFF_BUDGET_SEC
    spent_sec: float = field(default=0.0)

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_total_sec - self.spent_sec)

    def spend(self, seconds: float) -> None:
        self.spent_sec += max(0.0, seconds)


def _lock_for(provider: str) -> asyncio.Lock:
    if provider not in _locks:
        _locks[provider] = asyncio.Lock()
    return _locks[provider]


async def pace_before_request(provider: str) -> None:
    """Enforce minimum interval between calls to the same external API."""
    interval = INTERVALS.get(provider, 0.0)
    if interval <= 0:
        return
    async with _lock_for(provider):
        now = time.monotonic()
        elapsed = now - _last_request_at.get(provider, 0.0)
        wait = interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at[provider] = time.monotonic()


async def wait_after_429(
    provider: str,
    *,
    attempt: int,
    retry_after: int | None = None,
    budget: BackoffBudget | None = None,
) -> float:
    """Exponential backoff with jitter after HTTP 429."""
    if budget is not None and budget.remaining <= 0:
        raise BackoffBudgetExhausted(provider)

    base = max(BACKOFF_INITIAL_SEC, float(retry_after or 0))
    backoff = min(BACKOFF_MAX_SEC, base * (2**attempt))
    jitter = random.uniform(0, backoff * BACKOFF_JITTER_RATIO)
    total = backoff + jitter
    if budget is not None:
        total = min(total, budget.remaining)
        if total <= 0:
            raise BackoffBudgetExhausted(provider)

    _log.info(
        "%s 429 backoff attempt=%s wait=%.1fs",
        provider,
        attempt + 1,
        total,
    )
    await asyncio.sleep(total)
    if budget is not None:
        budget.spend(total)
    return total


def reset_for_tests() -> None:
    _last_request_at.clear()
