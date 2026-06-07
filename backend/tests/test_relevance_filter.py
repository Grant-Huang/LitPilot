"""Tests for LLM relevance filter before fetch."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.relevance_filter import (
    HIGH_REJECT_RATIO,
    MIN_HITS_FOR_QUERY_WARN,
    RelevanceDecision,
    apply_relevance_decisions,
    filter_hits_by_relevance,
    format_reject_report_lines,
    keep_all_hits,
    parse_relevance_json,
)


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
