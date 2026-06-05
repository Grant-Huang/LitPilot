"""Literature URL source strategy: merge vs user-only list."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LiteratureSourceMode = Literal["merge", "user_only"]
VALID_MODES = frozenset({"merge", "user_only"})


def normalize_literature_source_mode(mode: str | None) -> LiteratureSourceMode:
    m = (mode or "merge").strip().lower()
    if m in VALID_MODES:
        return m  # type: ignore[return-value]
    return "merge"


def should_skip_web_search(mode: LiteratureSourceMode, user_urls: list[str]) -> bool:
    return mode == "user_only" and bool(user_urls)


def hit_from_url(url: str) -> dict[str, str]:
    return {
        "url": url,
        "title": "",
        "snippet": "",
        "source": "upload",
    }


@dataclass
class FetchBuildResult:
    hits: list[dict[str, str]]
    user_count: int
    search_hit_count: int
    skipped_web_search: bool
    mode: LiteratureSourceMode
    used_user_only: bool


def build_fetch_hits(
    mode: str | None,
    search_hits: list[dict[str, str]],
    user_urls: list[str],
    *,
    max_urls: int,
) -> FetchBuildResult:
    """Build web_fetch queue from settings mode + web search + user URLs."""
    from app.agents.url_list import merge_fetch_hits

    norm = normalize_literature_source_mode(mode)

    if norm == "user_only" and user_urls:
        hits = [hit_from_url(u) for u in user_urls[:max_urls]]
        return FetchBuildResult(
            hits=hits,
            user_count=len(user_urls),
            search_hit_count=0,
            skipped_web_search=True,
            mode=norm,
            used_user_only=True,
        )

    if norm == "merge" and user_urls:
        merged, user_count = merge_fetch_hits(
            search_hits, user_urls, max_urls=max_urls
        )
        search_in = sum(1 for h in merged if h.get("source") != "upload")
        return FetchBuildResult(
            hits=merged,
            user_count=user_count,
            search_hit_count=search_in,
            skipped_web_search=False,
            mode=norm,
            used_user_only=False,
        )

    hits = [dict(h) for h in search_hits[:max_urls]]
    for h in hits:
        h.setdefault("source", "web_search")
    return FetchBuildResult(
        hits=hits,
        user_count=0,
        search_hit_count=len(hits),
        skipped_web_search=False,
        mode=norm,
        used_user_only=False,
    )
