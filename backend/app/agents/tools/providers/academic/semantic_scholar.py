"""Semantic Scholar Graph API search."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.agents.tools.providers.academic._hit import hit
from app.agents.tools.providers.academic.ss_rate_limit import (
    BackoffBudget,
    BackoffBudgetExhausted,
    pace_before_request,
    wait_after_429,
)

_log = logging.getLogger(__name__)

API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = ",".join([
    "title",
    "year",
    "authors",
    "citationCount",
    "abstract",
    "externalIds",
    "venue",
    "openAccessPdf",
])
# Keep total SS wall time within multi_academic per-source budget (see SOURCE_TIMEOUT_SEC).
SEARCH_TOTAL_TIMEOUT_SEC = 55.0
HTTP_TIMEOUT_SEC = 20.0
MAX_429_ATTEMPTS = 3


def _paper_url(paper: dict) -> str:
    ext = paper.get("externalIds") or {}
    if isinstance(ext, dict):
        arxiv_id = ext.get("ArXiv")
        if arxiv_id:
            return f"https://arxiv.org/abs/{arxiv_id}"
        doi = ext.get("DOI")
        if doi:
            return f"https://doi.org/{doi}"
    oa = paper.get("openAccessPdf") or {}
    if isinstance(oa, dict):
        u = str(oa.get("url") or "").strip()
        if u:
            return u
    return ""


def _normalize(paper: dict) -> dict[str, str] | None:
    url = _paper_url(paper)
    title = str(paper.get("title") or "").strip()
    if not url or not title:
        return None

    authors = paper.get("authors") or []
    names = [
        str(a.get("name") or "").strip()
        for a in authors[:3]
        if isinstance(a, dict) and a.get("name")
    ]
    if len(authors) > 3:
        names.append("et al.")

    venue = str(paper.get("venue") or "").strip()
    cites = paper.get("citationCount")
    snippet = str(paper.get("abstract") or "").strip()
    if not snippet and venue:
        snippet = f"{venue} · citations: {cites or 0}"

    return hit(
        url=url,
        title=title,
        snippet=snippet,
        source="Semantic Scholar",
    )


async def _search_once(
    *,
    params: dict[str, str | int],
    headers: dict[str, str],
    has_key: bool,
    min_year: int,
    limit: int,
    deadline: float,
) -> tuple[list[dict[str, str]] | None, int | None]:
    """Return (rows, None) on success; (None, retry_after) on 429; ([], None) on timeout."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return [], None

    await pace_before_request(has_api_key=has_key)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return [], None

    timeout = httpx.Timeout(
        min(HTTP_TIMEOUT_SEC, max(1.0, remaining)),
        connect=min(10.0, max(1.0, remaining)),
    )
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(API_BASE, params=params, headers=headers)
    if resp.status_code == 429:
        retry_after: int | None = None
        try:
            retry_after = int(resp.headers.get("Retry-After", "0") or 0)
        except ValueError:
            retry_after = None
        return None, retry_after
    resp.raise_for_status()
    papers = resp.json().get("data") or []
    rows: list[dict[str, str]] = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        if (p.get("year") or 0) < min_year:
            continue
        row = _normalize(p)
        if row:
            rows.append(row)
    return rows[:limit], None


async def search(
    query: str,
    *,
    limit: int = 8,
    min_year: int = 2019,
    api_key: str = "",
) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []

    has_key = bool(api_key)
    headers: dict[str, str] = {}
    if has_key:
        headers["x-api-key"] = api_key

    params = {"query": q[:300], "fields": FIELDS, "limit": max(1, min(limit, 25))}

    try:
        async with asyncio.timeout(SEARCH_TOTAL_TIMEOUT_SEC):
            return await _search_with_retries(
                params=params,
                headers=headers,
                has_key=has_key,
                min_year=min_year,
                limit=limit,
            )
    except TimeoutError:
        _log.warning("semantic_scholar search timed out query=%r", q[:80])
        return []


async def _search_with_retries(
    *,
    params: dict[str, str | int],
    headers: dict[str, str],
    has_key: bool,
    min_year: int,
    limit: int,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + SEARCH_TOTAL_TIMEOUT_SEC
    budget = BackoffBudget()
    for attempt in range(MAX_429_ATTEMPTS):
        try:
            rows, retry_after = await _search_once(
                params=params,
                headers=headers,
                has_key=has_key,
                min_year=min_year,
                limit=limit,
                deadline=deadline,
            )
        except httpx.HTTPError as exc:
            _log.warning("semantic_scholar HTTP error: %s", exc)
            return []
        if rows is not None:
            return rows
        if attempt >= MAX_429_ATTEMPTS - 1:
            return []
        if time.monotonic() >= deadline:
            return []
        try:
            await wait_after_429(
                attempt=attempt,
                retry_after=retry_after,
                budget=budget,
            )
        except BackoffBudgetExhausted:
            return []
        if time.monotonic() >= deadline:
            return []
    return []
