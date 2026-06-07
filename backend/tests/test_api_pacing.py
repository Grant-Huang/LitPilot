"""External API pacing tests."""
from __future__ import annotations

import time

import pytest

from app.agents.tools.providers.academic import api_pacing


@pytest.mark.asyncio
async def test_arxiv_pacing_enforces_interval() -> None:
    api_pacing.reset_for_tests()
    t0 = time.monotonic()
    await api_pacing.pace_before_request("arxiv")
    await api_pacing.pace_before_request("arxiv")
    elapsed = time.monotonic() - t0
    assert elapsed >= api_pacing.INTERVALS["arxiv"] * 0.9


@pytest.mark.asyncio
async def test_ncbi_pacing_enforces_interval() -> None:
    api_pacing.reset_for_tests()
    t0 = time.monotonic()
    await api_pacing.pace_before_request("ncbi")
    await api_pacing.pace_before_request("ncbi")
    elapsed = time.monotonic() - t0
    assert elapsed >= api_pacing.INTERVALS["ncbi"] * 0.9


@pytest.mark.asyncio
async def test_429_backoff_increases(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    monkeypatch.setattr("app.agents.tools.providers.academic.api_pacing.asyncio.sleep", fake_sleep)
    await api_pacing.wait_after_429("arxiv", attempt=0)
    await api_pacing.wait_after_429("arxiv", attempt=1)
    assert sleeps[1] > sleeps[0]


@pytest.mark.asyncio
async def test_429_backoff_budget_cap(monkeypatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(sec: float) -> None:
        sleeps.append(sec)

    monkeypatch.setattr("app.agents.tools.providers.academic.api_pacing.asyncio.sleep", fake_sleep)
    budget = api_pacing.BackoffBudget(max_total_sec=5.0)
    await api_pacing.wait_after_429("arxiv", attempt=0, budget=budget)
    with pytest.raises(api_pacing.BackoffBudgetExhausted):
        await api_pacing.wait_after_429("arxiv", attempt=1, budget=budget)
