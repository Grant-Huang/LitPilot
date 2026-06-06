"""Semantic Scholar rate limit pacing tests."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.agents.tools.providers.academic import ss_rate_limit


@pytest.mark.asyncio
async def test_pace_enforces_minimum_interval_no_key() -> None:
    ss_rate_limit.reset_for_tests()
    t0 = time.monotonic()
    await ss_rate_limit.pace_before_request(has_api_key=False)
    await ss_rate_limit.pace_before_request(has_api_key=False)
    elapsed = time.monotonic() - t0
    assert elapsed >= ss_rate_limit.BASE_INTERVAL_NO_KEY * 0.9


@pytest.mark.asyncio
async def test_pace_shorter_interval_with_key() -> None:
    ss_rate_limit.reset_for_tests()
    t0 = time.monotonic()
    await ss_rate_limit.pace_before_request(has_api_key=True)
    await ss_rate_limit.pace_before_request(has_api_key=True)
    elapsed = time.monotonic() - t0
    assert elapsed >= ss_rate_limit.BASE_INTERVAL_WITH_KEY * 0.9
    assert elapsed < ss_rate_limit.BASE_INTERVAL_NO_KEY * 0.95


@pytest.mark.asyncio
async def test_429_backoff_doubles_with_cap(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    monkeypatch.setattr("app.agents.tools.providers.academic.ss_rate_limit.asyncio.sleep", fake_sleep)
    await ss_rate_limit.wait_after_429(attempt=0, retry_after=None)
    await ss_rate_limit.wait_after_429(attempt=1, retry_after=None)
    await ss_rate_limit.wait_after_429(attempt=5, retry_after=None)
    assert sleeps[0] >= ss_rate_limit.BACKOFF_INITIAL_SEC
    assert sleeps[1] >= ss_rate_limit.BACKOFF_INITIAL_SEC * 2 * 0.9
    assert sleeps[2] <= ss_rate_limit.BACKOFF_MAX_SEC * (1 + ss_rate_limit.BACKOFF_JITTER_RATIO)
