"""CrossRef REST API search (metadata; no abstract)."""
from __future__ import annotations

import httpx

from app.agents.tools.providers.academic._hit import hit, merge_snippet

API_BASE = "https://api.crossref.org/works"
POLITE_EMAIL = "support@litpilot.local"


def _normalize_item(item: dict, query: str) -> dict[str, str] | None:
    titles = item.get("title") or []
    title = str(titles[0]).strip() if titles else ""
    if not title:
        return None

    authors_raw = item.get("author") or []
    names: list[str] = []
    for a in authors_raw[:3]:
        if not isinstance(a, dict):
            continue
        given = str(a.get("given") or "").strip()
        family = str(a.get("family") or "").strip()
        names.append(f"{family}, {given}".strip(", "))
    if len(authors_raw) > 3:
        names.append("et al.")

    year = None
    date_parts = (
        (item.get("published-print") or {}).get("date-parts")
        or (item.get("published-online") or {}).get("date-parts")
        or (item.get("created") or {}).get("date-parts")
    )
    if date_parts and date_parts[0]:
        try:
            year = int(date_parts[0][0])
        except (ValueError, IndexError, TypeError):
            year = None

    doi = str(item.get("DOI") or "").strip()
    if not doi:
        return None
    doi_url = f"https://doi.org/{doi}"

    container = item.get("container-title") or []
    venue = str(container[0]).strip() if container else str(item.get("publisher") or "")
    cites = item.get("is-referenced-by-count")
    snippet = merge_snippet(
        venue,
        ", ".join(names),
        f"citations: {cites}" if cites is not None else "",
    )

    row = hit(url=doi_url, title=title, snippet=snippet, source="CrossRef")
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
    email: str = POLITE_EMAIL,
) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []

    params = {
        "query": q[:300],
        "rows": max(1, min(limit, 25)),
        "sort": "relevance",
        "order": "desc",
        "filter": (
            f"from-pub-date:{min_year},type:journal-article,type:proceedings-article"
        ),
        "select": (
            "DOI,title,author,published-print,published-online,created,"
            "container-title,publisher,is-referenced-by-count,type"
        ),
    }
    headers = {"User-Agent": f"LitPilot/1.0 (mailto:{email})"}

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(API_BASE, params=params, headers=headers)
        if resp.status_code == 429:
            return []
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items") or []

    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = _normalize_item(item, q)
        if row and int(row.get("year") or 0) >= min_year:
            rows.append(row)
    return rows[:limit]
