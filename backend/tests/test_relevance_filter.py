"""Tests for LLM relevance filter before fetch."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.relevance_filter import (
    HIGH_REJECT_RATIO,
    MIN_HITS_FOR_QUERY_WARN,
    RelevanceDecision,
    RelevanceFilterResult,
    _filter_subtopic_hits_stream,
    apply_relevance_decisions,
    filter_hits_by_relevance,
    format_reject_report_lines,
    keep_all_hits,
    parse_relevance_json,
)
from app.core.think_stream import ThinkAccumulator


def test_parse_relevance_json() -> None:
    raw = """
    {
      "decisions": [
        {"index": 0, "score": 5, "keep": true, "reason": "核心"},
        {"index": 1, "score": 2, "keep": false, "reason": "偏题"}
      ],
      "summary": "总体尚可"
    }
    """
    hits = [
        {"url": "https://a.com/1", "title": "Paper A"},
        {"url": "https://a.com/2", "title": "Paper B"},
    ]
    decisions, summary = parse_relevance_json(raw, batch_offset=0, hits=hits)
    assert summary == "总体尚可"
    assert len(decisions) == 2
    assert decisions[0].keep is True
    assert decisions[1].keep is False


def test_apply_relevance_decisions_keeps_and_rejects() -> None:
    hits = [
        {"url": "https://a.com/1", "title": "Keep Me"},
        {"url": "https://a.com/2", "title": "Drop Me"},
    ]
    decisions = [
        RelevanceDecision(index=0, score=4, keep=True, reason="ok", title="Keep Me"),
        RelevanceDecision(index=1, score=1, keep=False, reason="no", title="Drop Me"),
    ]
    result = apply_relevance_decisions(hits, decisions)
    assert result.kept_count == 1
    assert result.rejected_count == 1
    assert result.kept_hits[0]["title"] == "Keep Me"
    assert result.rejected[0].title == "Drop Me"


def test_query_warning_when_high_reject_ratio() -> None:
    hits = [{"url": f"https://x.com/{i}", "title": f"T{i}"} for i in range(4)]
    decisions = [
        RelevanceDecision(index=i, score=1, keep=False, reason="x")
        for i in range(4)
    ]
    result = apply_relevance_decisions(hits, decisions)
    assert result.reject_ratio >= HIGH_REJECT_RATIO
    assert result.input_count >= MIN_HITS_FOR_QUERY_WARN
    assert result.query_warning is True
    lines = format_reject_report_lines(result)
    assert any("建议" in ln for ln in lines)


def test_keep_all_when_no_llm() -> None:
    hits = [{"url": "https://a.com", "title": "A"}]
    result = keep_all_hits(hits)
    assert result.kept_count == 1
    assert result.llm_used is False


@pytest.mark.asyncio
async def test_filter_hits_by_relevance_llm() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content=(
                '{"decisions": [{"index": 0, "score": 5, "keep": true, "reason": "相关"}],'
                '"summary": "ok"}'
            )
        )
    )
    hits = [{"url": "https://a.com", "title": "Good Paper", "snippet": "ml"}]
    result = await filter_hits_by_relevance(
        hits,
        user_message="machine learning survey",
        search_query="machine learning survey",
        llm=llm,
    )
    assert result.kept_count == 1
    assert result.llm_used is True
    llm.chat.assert_awaited_once()


def _make_streaming_llm(json_chunks: list[str]) -> MagicMock:
    """Build an LLM mock whose ``chat_stream_parts`` emits the given JSON chunks
    as ``content`` parts (so ``stream_llm_to_think`` can collect them and parse).
    """
    llm = MagicMock()

    async def _stream_parts(*_args, **_kwargs):
        for chunk in json_chunks:
            if chunk:
                yield ("content", chunk)

    llm.chat_stream_parts = _stream_parts
    llm.chat_stream = _stream_parts
    return llm


@pytest.mark.asyncio
async def test_filter_subtopic_hits_stream_emits_think_and_result() -> None:
    raw_json = (
        '{"decisions": [{"index": 0, "score": 4, "keep": true, "reason": "高度相关"}],'
        '"summary": "整体 OK"}'
    )
    llm = _make_streaming_llm([raw_json])
    think_acc = ThinkAccumulator()
    hits = [{"url": "https://a.com/1", "title": "Keep Me", "snippet": "x"}]
    events: list[tuple[str, dict]] = []
    final: RelevanceFilterResult | None = None
    async for ev in _filter_subtopic_hits_stream(
        hits=hits,
        user_message="user msg",
        search_query="q",
        llm=llm,
        think_acc=think_acc,
    ):
        events.append(ev)
        if ev[0] == "_filter_done":
            final = ev[1]
    assert final is not None
    assert final.kept_count == 1
    assert final.kept_hits[0]["title"] == "Keep Me"
    # think events should be forwarded to caller (model + done marker).
    think_events = [ev for ev in events if ev[0] == "think"]
    assert think_events, "expected at least one think SSE event"
    # The accumulated think content should be non-empty (content pieces joined).
    assert "Keep Me" in think_acc.finalize() or "高度相关" in think_acc.finalize()


@pytest.mark.asyncio
async def test_filter_subtopic_hits_stream_empty_hits_short_circuits() -> None:
    llm = _make_streaming_llm([])
    events: list[tuple[str, dict]] = []
    async for ev in _filter_subtopic_hits_stream(
        hits=[],
        user_message="user",
        search_query="q",
        llm=llm,
        think_acc=ThinkAccumulator(),
    ):
        events.append(ev)
    assert len(events) == 1
    assert events[0][0] == "_filter_done"
    assert events[0][1].kept_hits == []


@pytest.mark.asyncio
async def test_filter_subtopic_hits_stream_no_llm_keeps_all() -> None:
    llm = _make_streaming_llm([])
    hits = [{"url": "https://a.com", "title": "A"}]
    events: list[tuple[str, dict]] = []
    async for ev in _filter_subtopic_hits_stream(
        hits=hits,
        user_message="u",
        search_query="q",
        llm=None,
        think_acc=ThinkAccumulator(),
    ):
        events.append(ev)
    assert events[-1][0] == "_filter_done"
    assert events[-1][1].llm_used is False
    assert events[-1][1].kept_count == len(hits)


@pytest.mark.asyncio
async def test_filter_subtopic_hits_stream_falls_back_on_invalid_json() -> None:
    """When the LLM stream produces unparseable JSON, the stream helper keeps all
    hits and emits a single ``_filter_done`` with ``llm_used=False``-style summary.
    """
    llm = _make_streaming_llm(["not json at all"])
    hits = [{"url": "https://a.com", "title": "A"}]
    events: list[tuple[str, dict]] = []
    async for ev in _filter_subtopic_hits_stream(
        hits=hits,
        user_message="u",
        search_query="q",
        llm=llm,
        think_acc=ThinkAccumulator(),
    ):
        events.append(ev)
    # Last event should be _filter_done with kept_count == len(hits).
    assert events[-1][0] == "_filter_done"
    assert events[-1][1].kept_count == len(hits)
