"""Shared search query length limits and normalization (no router/aspect imports)."""
from __future__ import annotations

SEARCH_QUERY_MAX = 200
TOPIC_LABEL_MAX = 120


def clamp_search_query(
    text: str,
    *,
    max_len: int = SEARCH_QUERY_MAX,
    fallback: str = "",
) -> str:
    q = str(text or "").strip()[:max_len]
    if q:
        return q
    fb = str(fallback or "").strip()[:max_len]
    return fb
