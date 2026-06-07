"""First turn should not call router LLM."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.literature_intent import (
    build_session_turn_context,
    detect_intent_rules,
    route_literature_intent,
)
from app.agents.session_corpus import SessionCorpus


def _turn_ctx(*, has_corpus: bool = True, user_turns: int = 1):
    corpus = None
    if has_corpus:
        corpus = SessionCorpus()
        corpus.sources_md.append("## [网页材料] Sample\n\ncontent")
    with patch(
        "app.agents.literature_intent.list_session_library_items",
        return_value=[],
    ):
        return build_session_turn_context(
            session_id="s1",
            session_meta={"initial_query": "LLM survey", "gen_constraints": []},
            user_turns=user_turns,
            corpus=corpus,
            last_failed=[],
            has_review=False,
        )


def test_first_turn_rule_path_ignores_urls() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    result = detect_intent_rules(
        "AI-native manufacturing literature review",
        turn_ctx=ctx,
        extra_urls=["https://example.com/paper"],
    )
    assert result is not None
    assert result.intent == "new_topic"
    assert result.new_urls == []


@pytest.mark.asyncio
async def test_first_turn_skips_router_llm() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    with patch(
        "app.agents.literature_intent.get_router_llm",
        new=AsyncMock(),
    ) as mock_llm:
        result = await route_literature_intent(
            "AI-native manufacturing literature review",
            turn_ctx=ctx,
        )
    mock_llm.assert_not_called()
    assert result.intent == "new_topic"
    assert result.new_urls == []
