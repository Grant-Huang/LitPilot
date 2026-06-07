"""PubMed Central search via NCBI E-utilities (no API key)."""
from __future__ import annotations

import httpx

from app.agents.tools.providers.academic._hit import hit, merge_snippet
from app.agents.tools.providers.academic.api_pacing import (
    BackoffBudget,
    BackoffBudgetExhausted,
    pace_before_request,
    wait_after_429,
)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PMC_ARTICLE_BASE = "https://www.ncbi.nlm.nih.gov/pmc/articles"
_USER_AGENT = "LitPilot/1.0 (mailto:support@litpilot.local)"
MAX_ATTEMPTS = 4


async def _esearch(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    min_year: int,
    *,
    budget: BackoffBudget | None = None,
) -> list[str]:
    params = {
        "db": "pmc",
        "term": query[:300],
        "retmax": max(1, min(limit, 25)),
        "retmode": "json",
        "sort": "relevance",
        "mindate": str(min_year),
        "maxdate": "3000",
        "datetype": "pdat",
    }
    for attempt in range(MAX_ATTEMPTS):
        await pace_before_request("ncbi")
        resp = await client.get(ESEARCH_URL, params=params)
        if resp.status_code == 429:
            if attempt + 1 >= MAX_ATTEMPTS:
                return []
            try:
                await wait_after_429("ncbi", attempt=attempt, budget=budget)
            except BackoffBudgetExhausted:
                return []
            continue
        resp.raise_for_status()
        data = resp.json()
        return list(data.get("esearchresult", {}).get("idlist") or [])
    return []


async def _esummary(
    client: httpx.AsyncClient,
    pmc_ids: list[str],
    *,
    budget: BackoffBudget | None = None,
) -> list[dict]:
    if not pmc_ids:
        return []
    params = {
        "db": "pmc",
        "id": ",".join(pmc_ids),
        "retmode": "json",
    }
    for attempt in range(MAX_ATTEMPTS):
        await pace_before_request("ncbi")
        resp = await client.get(ESUMMARY_URL, params=params)
        if resp.status_code == 429:
            if attempt + 1 >= MAX_ATTEMPTS:
                return []
            try:
                await wait_after_429("ncbi", attempt=attempt, budget=budget)
            except BackoffBudgetExhausted:
                return []
            continue
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        uids = result.get("uids") or []
        return [result[uid] for uid in uids if uid in result and isinstance(result[uid], dict)]
    return []


def _normalize(article: dict, query: str) -> dict[str, str] | None:
    pmc_id = str(article.get("uid") or "").strip()
    if not pmc_id:
        return None
    page_url = f"{PMC_ARTICLE_BASE}/PMC{pmc_id}/"

    authors_raw = article.get("authors") or []
    names = [
        str(a.get("name") or "").strip()
        for a in authors_raw[:3]
        if isinstance(a, dict) and a.get("name")
    ]
    if len(authors_raw) > 3:
        names.append("et al.")

    pub_date = str(article.get("pubdate") or "")
    year = None
    if pub_date:
        try:
            year = int(pub_date.split()[0])
        except (ValueError, IndexError):
            year = None

    title = str(article.get("title") or "").strip()
    venue = str(article.get("source") or "").strip()
    snippet = merge_snippet(venue, ", ".join(names))

    row = hit(url=page_url, title=title, snippet=snippet, source="PMC")
    row["year"] = str(year or "")
    row["query"] = query
    if year is None:
        return None
    return row


async def search(
    query: str,
    *,
    limit: int = 8,
    min_year: int = 2019,
) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        budget = BackoffBudget()
        pmc_ids = await _esearch(client, q, limit, min_year, budget=budget)
        if not pmc_ids:
            return []
        articles = await _esummary(client, pmc_ids, budget=budget)

    rows: list[dict[str, str]] = []
    for art in articles:
        row = _normalize(art, q)
        if row and int(row.get("year") or 0) >= min_year:
            rows.append(row)
    return rows[:limit]
