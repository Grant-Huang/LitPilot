"""Tests for search hit merge (M6)."""
from __future__ import annotations

from app.agents.search_merge import merge_search_hits


def test_merge_deduplicates_by_url() -> None:
    a = [{"url": "https://arxiv.org/abs/1", "title": "A"}]
    b = [{"url": "https://arxiv.org/abs/1", "title": "A dup"}]
    c = [{"url": "https://arxiv.org/abs/2", "title": "B"}]
    merged = merge_search_hits([a, b, c])
    assert len(merged) == 2
    titles = {h["title"] for h in merged}
    assert "A" in titles
    assert "B" in titles


def test_merge_respects_max_results() -> None:
    lists = [[{"url": f"https://x.com/{i}", "title": str(i)}] for i in range(5)]
    merged = merge_search_hits(lists, max_results=3)
    assert len(merged) == 3
