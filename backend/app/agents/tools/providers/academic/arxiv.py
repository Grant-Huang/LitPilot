"""arXiv Atom API search (no API key)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from app.agents.tools.providers.academic._hit import hit

API_BASE = "https://export.arxiv.org/api/query"
DEFAULT_CATEGORIES = "cs.AI OR cs.MA OR cs.SE OR eess.SY"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _text(el, tag: str, ns: str = "atom") -> str:
    node = el.find(f"{ns}:{tag}", _NS)
    return node.text.strip() if node is not None and node.text else ""


def _parse_entry(entry) -> tuple[dict[str, str], int] | None:
    authors = entry.findall("atom:author", _NS)
    names = [
        a.find("atom:name", _NS).text.strip()
        for a in authors[:3]
        if a.find("atom:name", _NS) is not None and a.find("atom:name", _NS).text
    ]
    if len(authors) > 3:
        names.append("et al.")

    raw_id = _text(entry, "id")
    if "/abs/" not in raw_id:
        return None
    arxiv_id = raw_id.split("/abs/")[-1].split("v")[0]
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"

    published = _text(entry, "published")
    if len(published) < 4:
        return None
    try:
        year = int(published[:4])
    except ValueError:
        return None

    journal_ref_el = entry.find("arxiv:journal_ref", _NS)
    venue = (
        journal_ref_el.text.strip()
        if journal_ref_el is not None and journal_ref_el.text
        else "arXiv preprint"
    )
    abstract = _text(entry, "summary").replace("\n", " ")

    row = hit(
        url=abs_url,
        title=_text(entry, "title").replace("\n", " "),
        snippet=abstract or venue,
        source="arXiv",
    )
    return row, year


async def search(
    query: str,
    *,
    limit: int = 8,
    min_year: int = 2019,
    categories: str = DEFAULT_CATEGORIES,
) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []

    search_query = f"({q}) AND ({categories})" if categories else q
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max(1, min(limit, 25)),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(API_BASE, params=params)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

    rows: list[dict[str, str]] = []
    for entry in root.findall("atom:entry", _NS):
        parsed = _parse_entry(entry)
        if not parsed:
            continue
        row, year = parsed
        if year >= min_year:
            rows.append(row)
    return rows[:limit]
