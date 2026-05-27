from __future__ import annotations

from typing import Any

import httpx

ACADEMIC_SEARCH_DOMAINS: tuple[str, ...] = (
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "jmlr.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "semanticscholar.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "biorxiv.org",
    "medrxiv.org",
    "ssrn.com",
    "link.springer.com",
    "nature.com",
    "science.org",
    "sciencedirect.com",
    "wiley.com",
    "frontiersin.org",
    "plos.org",
    "mdpi.com",
)


def build_tavily_search_payload(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": False,
    }
    if include_domains:
        payload["include_domains"] = list(include_domains)
    if exclude_domains:
        payload["exclude_domains"] = list(exclude_domains)
    return payload


async def tavily_search(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
    include_domains: list[str] | tuple[str, ...] | None = None,
    exclude_domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Tavily API Key 未配置")

    payload = build_tavily_search_payload(
        api_key,
        query,
        max_results=max_results,
        search_depth=search_depth,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post("https://api.tavily.com/search", json=payload)
        resp.raise_for_status()
        return resp.json()


def normalize_tavily_results(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        rows.append({
            "url": url,
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("content") or "")[:800],
        })
    return rows
