"""Semantic Scholar Graph API search."""
from __future__ import annotations

import httpx

from app.agents.tools.providers.academic._hit import hit
from app.agents.tools.providers.academic.ss_rate_limit import (
    pace_before_request,
    wait_after_429,
)

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
MAX_429_ATTEMPTS = 6


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

    for attempt in range(MAX_429_ATTEMPTS):
        await pace_before_request(has_api_key=has_key)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(API_BASE, params=params, headers=headers)
        if resp.status_code == 429:
            if attempt >= MAX_429_ATTEMPTS - 1:
                return []
            retry_after: int | None = None
            try:
                retry_after = int(resp.headers.get("Retry-After", "0") or 0)
            except ValueError:
                retry_after = None
            await wait_after_429(attempt=attempt, retry_after=retry_after)
            continue
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
        return rows[:limit]
    return []
