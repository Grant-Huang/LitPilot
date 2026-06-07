"""First turn should not call route_literature before Checkpoint A."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.literature_intent import (
    build_session_turn_context,
    route_literature_intent,
)
from app.agents.session_corpus import SessionCorpus


def _turn_ctx(*, has_corpus: bool = True, user_turns: int = 1):
    corpus = None
    if has_corpus:
        corpus = SessionCorpus()
        corpus.sources_md.append("## [网页材料] Sample\n\ncontent")
    return build_session_turn_context(
        session_id="s1",
        session_meta={"initial_query": "LLM survey", "gen_constraints": []},
        user_turns=user_turns,
        corpus=corpus,
        last_failed=[],
        has_review=False,
    )


@pytest.mark.asyncio
async def test_first_turn_skips_route_literature_llm() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    with patch(
        "app.agents.literature_intent.route_literature",
        new=AsyncMock(),
    ) as mock_route:
        result = await route_literature_intent(
            "AI-native manufacturing literature review",
            turn_ctx=ctx,
        )
    mock_route.assert_not_called()
    assert result.intent == "new_topic"
    assert result.search_query
