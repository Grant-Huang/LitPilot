"""Global Semantic Scholar request pacing (interval + 429 exponential backoff)."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

_lock = asyncio.Lock()
_last_request_at = 0.0

# 20% headroom over documented limits (~3 req/s anonymous, ~10 req/s with key)
BASE_INTERVAL_NO_KEY = 3.5
BASE_INTERVAL_WITH_KEY = 1.1

BACKOFF_INITIAL_SEC = 8.0
BACKOFF_MAX_SEC = 120.0
BACKOFF_JITTER_RATIO = 0.2
BACKOFF_BUDGET_SEC = 30.0


class BackoffBudgetExhausted(Exception):
    """Raised when cumulative 429 backoff exceeds the per-request budget."""


@dataclass
class BackoffBudget:
    max_total_sec: float = BACKOFF_BUDGET_SEC
    spent_sec: float = field(default=0.0)

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_total_sec - self.spent_sec)

    def spend(self, seconds: float) -> None:
        self.spent_sec += max(0.0, seconds)


async def pace_before_request(*, has_api_key: bool) -> None:
    """Enforce minimum interval between SS API calls (process-wide)."""
    global _last_request_at
    interval = BASE_INTERVAL_WITH_KEY if has_api_key else BASE_INTERVAL_NO_KEY
    async with _lock:
        now = time.monotonic()
        elapsed = now - _last_request_at
        wait = interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


async def wait_after_429(
    *,
    attempt: int,
    retry_after: int | None = None,
    budget: BackoffBudget | None = None,
) -> float:
    """Exponential backoff with jitter after HTTP 429. Returns seconds waited."""
    if budget is not None and budget.remaining <= 0:
        raise BackoffBudgetExhausted()

    base = max(BACKOFF_INITIAL_SEC, float(retry_after or 0))
    backoff = min(BACKOFF_MAX_SEC, base * (2**attempt))
    jitter = random.uniform(0, backoff * BACKOFF_JITTER_RATIO)
    total = backoff + jitter
    if budget is not None:
        total = min(total, budget.remaining)
        if total <= 0:
            raise BackoffBudgetExhausted()

    _log.info(
        "SS 429 backoff attempt=%s wait=%.1fs (base=%.1f cap=%.1f)",
        attempt + 1,
        total,
        backoff,
        BACKOFF_MAX_SEC,
    )
    await asyncio.sleep(total)
    if budget is not None:
        budget.spend(total)
    return total


def reset_for_tests() -> None:
    global _last_request_at
    _last_request_at = 0.0
