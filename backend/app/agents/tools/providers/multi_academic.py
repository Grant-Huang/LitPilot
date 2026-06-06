"""Parallel multi-source academic web_search (arXiv, CrossRef, PMC, OpenAlex, SS)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.agents.tools.providers import openalex as openalex_provider
from app.agents.tools.providers.academic import arxiv, crossref, pubmed, semantic_scholar
from app.agents.tools.search_hits import restrict_hits_to_domains

_log = logging.getLogger(__name__)

DEFAULT_MIN_YEAR = 2019


async def _run_source(name: str, coro) -> list[dict[str, str]]:
    try:
        rows = await coro
        if isinstance(rows, dict):
            return list(rows.get("results") or [])
        return list(rows or [])
    except Exception as exc:
        _log.warning("multi_academic source %s failed: %s", name, exc)
        return []


async def search(
    query: str,
    *,
    max_results: int = 8,
    min_year: int = DEFAULT_MIN_YEAR,
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
    s2_api_key: str = "",
    **_kwargs: Any,
) -> dict[str, Any]:
    _ = exclude_domains
    q = (query or "").strip()
    if len(q) < 2:
        return {"results": [], "answer": ""}

    per_source = max(3, min(12, max_results))

    openalex_coro = openalex_provider.search(
        q,
        max_results=per_source,
        include_domains=None,
    )
    tasks = {
        "openalex": _run_source("openalex", openalex_coro),
        "arxiv": _run_source(
            "arxiv",
            arxiv.search(q, limit=per_source, min_year=min_year),
        ),
        "crossref": _run_source(
            "crossref",
            crossref.search(q, limit=per_source, min_year=min_year),
        ),
        "pubmed": _run_source(
            "pubmed",
            pubmed.search(q, limit=per_source, min_year=min_year),
        ),
        "semantic_scholar": _run_source(
            "semantic_scholar",
            semantic_scholar.search(
                q,
                limit=per_source,
                min_year=min_year,
                api_key=s2_api_key,
            ),
        ),
    }

    gathered = await asyncio.gather(*tasks.values())
    by_name = dict(zip(tasks.keys(), gathered, strict=True))

    from app.agents.search_merge import merge_search_hits

    hit_lists = [rows for rows in gathered if rows]
    merged = merge_search_hits(hit_lists, max_results=max_results)

    if include_domains:
        merged = restrict_hits_to_domains(merged, include_domains=include_domains)

    counts = {k: len(v) for k, v in by_name.items()}
    _log.info(
        "multi_academic query=%r per_source=%s counts=%s merged=%s",
        q[:80],
        per_source,
        counts,
        len(merged),
    )

    return {"results": merged, "answer": "", "source_counts": counts}
