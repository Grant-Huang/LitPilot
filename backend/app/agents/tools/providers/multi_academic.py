"""Parallel multi-source academic web_search (arXiv, CrossRef, PMC, OpenAlex, SS)."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.agents.tools.providers import openalex as openalex_provider
from app.agents.tools.providers.academic import arxiv, crossref, pubmed, semantic_scholar
from app.agents.tools.providers.academic.source_gate import (
    SOURCE_NAMES,
    source_count,
    source_slot,
)
from app.agents.tools.search_hits import restrict_hits_to_domains

_log = logging.getLogger(__name__)

DEFAULT_MIN_YEAR = 2019
SOURCE_TIMEOUT_SEC = 90.0
SOURCE_TIMEOUTS: dict[str, float] = {
    "semantic_scholar": 60.0,
}

SOURCE_LABELS = {
    "openalex": "OpenAlex",
    "arxiv": "arXiv",
    "crossref": "CrossRef",
    "pubmed": "PubMed",
    "semantic_scholar": "Semantic Scholar",
}


@dataclass(frozen=True)
class PassSpec:
    pass_index: int
    pass_total: int
    query: str
    topic_title: str
    max_results: int


async def _run_source(name: str, coro) -> list[dict[str, str]]:
    try:
        rows = await coro
        if isinstance(rows, dict):
            return list(rows.get("results") or [])
        return list(rows or [])
    except Exception as exc:
        _log.warning("multi_academic source %s failed: %s", name, exc)
        return []


def _top_hits(rows: list[dict[str, str]], limit: int = 3) -> list[dict[str, str]]:
    from app.agents.url_list import title_from_search_hit

    out: list[dict[str, str]] = []
    for row in rows:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        title = str(row.get("title") or "").strip()
        if not title or title == url:
            title = title_from_search_hit(row)
        out.append({"url": url, "title": (title or url)[:200]})
        if len(out) >= limit:
            break
    return out


def _top_urls(rows: list[dict[str, str]], limit: int = 3) -> list[str]:
    return [h["url"] for h in _top_hits(rows, limit=limit)]


def _source_coro(
    name: str,
    query: str,
    *,
    per_source: int,
    min_year: int,
    s2_api_key: str,
):
    if name == "openalex":
        return openalex_provider.search(
            query,
            max_results=per_source,
            include_domains=None,
        )
    if name == "arxiv":
        return arxiv.search(query, limit=per_source, min_year=min_year)
    if name == "crossref":
        return crossref.search(query, limit=per_source, min_year=min_year)
    if name == "pubmed":
        return pubmed.search(query, limit=per_source, min_year=min_year)
    if name == "semantic_scholar":
        return semantic_scholar.search(
            query,
            limit=per_source,
            min_year=min_year,
            api_key=s2_api_key,
        )
    raise KeyError(name)


async def _search_one_source(
    name: str,
    query: str,
    *,
    max_results: int,
    min_year: int,
    s2_api_key: str,
) -> tuple[list[dict[str, str]], bool]:
    """Run one source for one query; holds the global per-source slot."""
    per_source = max(1, int(max_results))
    async with source_slot(name):
        return await _bounded(
            name,
            _source_coro(
                name,
                query,
                per_source=per_source,
                min_year=min_year,
                s2_api_key=s2_api_key,
            ),
        )


async def _bounded(name: str, coro) -> tuple[str, list[dict[str, str]], bool]:
    timeout = SOURCE_TIMEOUTS.get(name, SOURCE_TIMEOUT_SEC)
    try:
        async with asyncio.timeout(timeout):
            rows = await _run_source(name, coro)
        return name, rows, False
    except TimeoutError:
        _log.warning("multi_academic source %s timed out after %.0fs", name, timeout)
        return name, [], True
    except Exception as exc:
        _log.warning("multi_academic source %s failed: %s", name, exc)
        return name, [], True


def _source_done_payload(
    name: str,
    rows: list[dict[str, str]],
    *,
    max_results: int,
    failed: bool,
    query: str,
) -> dict[str, Any]:
    found = len(rows)
    taken = min(found, max_results)
    return {
        "source": name,
        "label": SOURCE_LABELS.get(name, name),
        "query": query,
        "hits": found,
        "hits_found": found,
        "hits_taken": taken,
        "max_results": max_results,
        "top_urls": _top_urls(rows[:max_results]),
        "top_hits": _top_hits(rows[:max_results]),
        "failed": failed,
    }


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
    """Single pass: parallel across sources (each source at most one slot)."""
    _ = exclude_domains
    q = (query or "").strip()
    if len(q) < 2:
        yield ("complete", {"results": [], "answer": "", "source_counts": {}})
        return

    per_source = max(1, int(max_results))

    async def _run_one(name: str) -> tuple[str, list[dict[str, str]], bool]:
        _name, rows, failed = await _search_one_source(
            name,
            q,
            max_results=max_results,
            min_year=min_year,
            s2_api_key=s2_api_key,
        )
        return _name, rows, failed

    tasks: dict[str, asyncio.Task[tuple[str, list[dict[str, str]], bool]]] = {}
    for name in SOURCE_NAMES:
        tasks[name] = asyncio.create_task(_run_one(name))
        yield (
            "source_start",
            {
                "source": name,
                "label": SOURCE_LABELS.get(name, name),
                "query": q,
                "max_results": max_results,
            },
        )

    by_name: dict[str, list[dict[str, str]]] = {}
    pending = set(tasks.keys())
    loop_deadline = time.monotonic() + SOURCE_TIMEOUT_SEC + 15.0
    try:
        while pending:
            wait_sec = max(0.1, loop_deadline - time.monotonic())
            if wait_sec <= 0:
                _log.warning(
                    "multi_academic gather deadline exceeded; pending=%s query=%r",
                    sorted(pending),
                    q[:80],
                )
                break
            done_set, _pending_set = await asyncio.wait(
                [tasks[n] for n in pending],
                timeout=wait_sec,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done_set:
                _log.warning(
                    "multi_academic wait stalled; pending=%s query=%r",
                    sorted(pending),
                    q[:80],
                )
                break
            for finished in done_set:
                name, rows, failed = await finished
                pending.discard(name)
                by_name[name] = rows
                yield (
                    "source_done",
                    _source_done_payload(
                        name,
                        rows,
                        max_results=max_results,
                        failed=failed,
                        query=q,
                    ),
                )
    finally:
        for task in tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)

    for name in pending:
        by_name.setdefault(name, [])
        yield (
            "source_done",
            _source_done_payload(
                name,
                [],
                max_results=max_results,
                failed=True,
                query=q,
            ),
        )

    async for kind, payload in _complete_from_by_name(
        by_name,
        query=q,
        max_results=max_results,
        per_source=per_source,
        include_domains=include_domains,
    ):
        yield kind, payload


async def _complete_from_by_name(
    by_name: dict[str, list[dict[str, str]]],
    *,
    query: str,
    max_results: int,
    per_source: int,
    include_domains: list[str] | tuple[str, ...] | None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.search_merge import merge_search_hits

    hit_lists = [rows for rows in by_name.values() if rows]
    raw_found_total = sum(len(rows) for rows in by_name.values())
    merged = merge_search_hits(hit_lists)
    if include_domains:
        merged = restrict_hits_to_domains(merged, include_domains=include_domains)

    counts = {k: len(v) for k, v in by_name.items()}
    _log.info(
        "multi_academic query=%r per_source=%s counts=%s merged=%s",
        query[:80],
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
            "raw_found_total": raw_found_total,
            "hits_taken": len(merged),
        },
    )


async def iter_multi_pass_by_source_events(
    passes: list[PassSpec],
    *,
    min_year: int = DEFAULT_MIN_YEAR,
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
    s2_api_key: str = "",
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Multi pass: one worker per source; topics serialized per source, sources in parallel."""
    _ = exclude_domains
    if not passes:
        return

    event_q: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    pass_rows: dict[int, dict[str, list[dict[str, str]]]] = {
        spec.pass_index: {} for spec in passes
    }

    async def _source_worker(source_name: str) -> None:
        for spec in passes:
            q = (spec.query or "").strip()
            if len(q) < 2:
                continue
            pass_meta = {
                "query": q,
                "pass_index": spec.pass_index,
                "pass_total": spec.pass_total,
                "topic_title": spec.topic_title or "",
                "provider": "multi_academic",
            }
            await event_q.put(
                (
                    "source_start",
                    {
                        **pass_meta,
                        "source": source_name,
                        "label": SOURCE_LABELS.get(source_name, source_name),
                        "max_results": spec.max_results,
                    },
                ),
            )
            _name, rows, failed = await _search_one_source(
                source_name,
                q,
                max_results=spec.max_results,
                min_year=min_year,
                s2_api_key=s2_api_key,
            )
            pass_rows[spec.pass_index][source_name] = rows
            await event_q.put(
                (
                    "source_done",
                    {
                        **pass_meta,
                        **_source_done_payload(
                            source_name,
                            rows,
                            max_results=spec.max_results,
                            failed=failed,
                            query=q,
                        ),
                    },
                ),
            )
        await event_q.put(None)

    workers = [asyncio.create_task(_source_worker(name)) for name in SOURCE_NAMES]
    finished_workers = 0
    try:
        while finished_workers < len(workers):
            item = await event_q.get()
            if item is None:
                finished_workers += 1
                continue
            yield item
    finally:
        for w in workers:
            if not w.done():
                w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    from app.agents.search_merge import merge_search_hits

    for spec in passes:
        q = (spec.query or "").strip()
        by_name = pass_rows.get(spec.pass_index) or {}
        hit_lists = [rows for rows in by_name.values() if rows]
        raw_found_total = sum(len(rows) for rows in by_name.values())
        merged = merge_search_hits(hit_lists)
        if include_domains:
            merged = restrict_hits_to_domains(merged, include_domains=include_domains)
        counts = {k: len(v) for k, v in by_name.items()}
        yield (
            "pass_complete",
            {
                "pass_index": spec.pass_index,
                "pass_total": spec.pass_total,
                "query": q,
                "topic_title": spec.topic_title,
                "results": merged,
                "source_counts": counts,
                "raw_found_total": raw_found_total,
                "hits_taken": len(merged),
            },
        )
