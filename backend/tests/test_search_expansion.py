"""Tests for search query expansion (M6)."""
from __future__ import annotations

import pytest

from app.agents.search_expansion import (
    expand_search_queries_rule,
    expand_search_queries,
)


def test_expand_rule_includes_base() -> None:
    queries = expand_search_queries_rule("transformer efficiency", count=3)
    assert queries[0] == "transformer efficiency"
    assert len(queries) == 3
    assert any("survey" in q.lower() for q in queries[1:])


def test_expand_rule_single() -> None:
    assert expand_search_queries_rule("topic", count=1) == ["topic"]


@pytest.mark.asyncio
async def test_expand_without_llm_uses_rules() -> None:
    queries = await expand_search_queries(
        "graph neural networks",
        count=2,
        llm=None,
        use_llm=False,
    )
    assert queries[0] == "graph neural networks"
    assert len(queries) == 2
