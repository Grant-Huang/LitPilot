"""Merge and deduplicate Tavily search hit lists."""
from __future__ import annotations

from app.library.canonical import canonical_key, normalize_url


def merge_search_hits(
    hits_lists: list[list[dict[str, str]]],
    *,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for hits in hits_lists:
        for hit in hits:
            url = str(hit.get("url") or "").strip()
            if not url:
                continue
            key = canonical_key(url=url) or normalize_url(url) or url
            if key in seen:
                continue
            seen.add(key)
            merged.append(hit)
            if max_results is not None and len(merged) >= max_results:
                return merged
    return merged
