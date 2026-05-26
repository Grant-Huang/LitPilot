from __future__ import annotations

from typing import Any

import httpx


async def tavily_search(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("Tavily API Key 未配置")

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
        "include_raw_content": False,
    }
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
