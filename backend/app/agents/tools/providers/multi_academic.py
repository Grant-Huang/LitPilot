"""Parallel multi-source academic web_search (arXiv, CrossRef, PMC, OpenAlex, SS)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agents.tools.providers import openalex as openalex_provider
from app.agents.tools.providers.academic import arxiv, crossref, pubmed, semantic_scholar
from app.agents.tools.search_hits import restrict_hits_to_domains

_log = logging.getLogger(__name__)

DEFAULT_MIN_YEAR = 2019
SOURCE_TIMEOUT_SEC = 120.0

SOURCE_LABELS = {
    "openalex": "OpenAlex",
    "arxiv": "arXiv",
    "crossref": "CrossRef",
    "pubmed": "PubMed",
    "semantic_scholar": "Semantic Scholar",
}


async def _run_source(name: str, coro) -> list[dict[str, str]]:
    try:
        rows = await coro
        if isinstance(rows, dict):
            return list(rows.get("results") or [])
        return list(rows or [])
    except Exception as exc:
        _log.warning("multi_academic source %s failed: %s", name, exc)
        return []


def _top_urls(rows: list[dict[str, str]], limit: int = 3) -> list[str]:
    out: list[str] = []
    for row in rows:
        url = str(row.get("url") or "").strip()
        if url and url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out


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
    merged: dict[str, Any] = {"results": [], "answer": "", "source_counts": {}}
    async for kind, payload in iter_search_events(
        query,
        max_results=max_results,
        min_year=min_year,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        s2_api_key=s2_api_key,
    ):
        if kind == "complete":
            merged = payload
    return merged


async def iter_search_events(
    query: str,
    *,
    max_results: int = 8,
    min_year: int = DEFAULT_MIN_YEAR,
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
    s2_api_key: str = "",
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield source_start / source_done / complete for SSE progress."""
    _ = exclude_domains
    q = (query or "").strip()
    if len(q) < 2:
        yield ("complete", {"results": [], "answer": "", "source_counts": {}})
        return

    per_source = max(3, min(12, max_results))

    async def _bounded(name: str, coro) -> tuple[str, list[dict[str, str]]]:
        try:
            rows = await asyncio.wait_for(
                _run_source(name, coro),
                timeout=SOURCE_TIMEOUT_SEC,
            )
            return name, rows
        except asyncio.TimeoutError:
            _log.warning("multi_academic source %s timed out", name)
            return name, []
        except Exception as exc:
            _log.warning("multi_academic source %s failed: %s", name, exc)
            return name, []

    coros = {
        "openalex": openalex_provider.search(
            q,
            max_results=per_source,
            include_domains=None,
        ),
        "arxiv": arxiv.search(q, limit=per_source, min_year=min_year),
        "crossref": crossref.search(q, limit=per_source, min_year=min_year),
        "pubmed": pubmed.search(q, limit=per_source, min_year=min_year),
        "semantic_scholar": semantic_scholar.search(
            q,
            limit=per_source,
            min_year=min_year,
            api_key=s2_api_key,
        ),
    }

    tasks: dict[str, asyncio.Task[tuple[str, list[dict[str, str]]]]] = {}
    for name, coro in coros.items():
        tasks[name] = asyncio.create_task(_bounded(name, coro))
        yield (
            "source_start",
            {
                "source": name,
                "label": SOURCE_LABELS.get(name, name),
                "query": q,
                "expected": per_source,
            },
        )

    by_name: dict[str, list[dict[str, str]]] = {}
    try:
        for finished in asyncio.as_completed(tasks.values()):
            name, rows = await finished
            by_name[name] = rows
            yield (
                "source_done",
                {
                    "source": name,
                    "label": SOURCE_LABELS.get(name, name),
                    "hits": len(rows),
                    "expected": per_source,
                    "top_urls": _top_urls(rows),
                },
            )
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)

    from app.agents.search_merge import merge_search_hits

    hit_lists = [rows for rows in by_name.values() if rows]
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
    yield (
        "complete",
        {
            "results": merged,
            "answer": "",
            "source_counts": counts,
            "per_source": per_source,
        },
    )
