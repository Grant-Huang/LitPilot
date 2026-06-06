"""Tests for per-source gate and multi-pass by-source scheduler."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.agents.tools.providers import multi_academic as ma
from app.agents.tools.providers.academic import source_gate


@pytest.mark.asyncio
async def test_source_gate_serializes_same_source() -> None:
    source_gate.reset_for_tests()
    order: list[str] = []

    async def worker(tag: str) -> None:
        async with source_gate.source_slot("arxiv"):
            order.append(f"{tag}-start")
            await asyncio.sleep(0.05)
            order.append(f"{tag}-end")

    await asyncio.gather(worker("a"), worker("b"))
    assert order.index("a-start") < order.index("a-end")
    assert order.index("b-start") < order.index("b-end")
    # One worker fully finishes before the other starts on the same source slot.
    assert order == ["a-start", "a-end", "b-start", "b-end"] or order == [
        "b-start",
        "b-end",
        "a-start",
        "a-end",
    ]


@pytest.mark.asyncio
async def test_iter_multi_pass_by_source_one_slot_per_source(monkeypatch) -> None:
    source_gate.reset_for_tests()
    in_flight: dict[str, int] = {name: 0 for name in source_gate.SOURCE_NAMES}
    peak: dict[str, int] = {name: 0 for name in source_gate.SOURCE_NAMES}

    async def fake_search_one(name: str, query: str, **kwargs):
        in_flight[name] += 1
        peak[name] = max(peak[name], in_flight[name])
        await asyncio.sleep(0.02)
        in_flight[name] -= 1
        return name, [{"url": f"https://example.com/{name}/{query[:4]}", "title": "t"}], False

    monkeypatch.setattr(ma, "_search_one_source", fake_search_one)

    passes = [
        ma.PassSpec(1, 2, "query-one", "主题一", 5),
        ma.PassSpec(2, 2, "query-two", "主题二", 5),
    ]
    events: list[tuple[str, dict]] = []
    async for kind, payload in ma.iter_multi_pass_by_source_events(passes):
        events.append((kind, payload))

    for name in source_gate.SOURCE_NAMES:
        assert peak[name] == 1

    pass_complete = [p for k, p in events if k == "pass_complete"]
    assert len(pass_complete) == 2
    assert all(p.get("hits_taken", 0) >= 1 for p in pass_complete)
