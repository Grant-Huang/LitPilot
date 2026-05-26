from __future__ import annotations

from typing import Any

import httpx

from app.agents.ttl_cache import jina_cache, normalize_cache_key, tavily_cache
from app.agents.tools.jina_reader import jina_fetch
from app.agents.tools.tavily_search import tavily_search


async def cached_tavily_search(
    api_key: str,
    query: str,
    *,
    max_results: int = 8,
    search_depth: str = "advanced",
) -> dict[str, Any]:
    key = normalize_cache_key(
        "tavily",
        query,
        {"max_results": max_results, "search_depth": search_depth},
    )
    hit = tavily_cache.get(key)
    if hit is not None:
        return hit
    data = await tavily_search(
        api_key,
        query,
        max_results=max_results,
        search_depth=search_depth,
    )
    tavily_cache.set(key, data)
    return data


async def cached_jina_fetch(
    url: str,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> str:
    key = normalize_cache_key("jina", url, {"timeout": timeout})
    hit = jina_cache.get(key)
    if hit is not None:
        return hit
    text = await jina_fetch(url, api_key=api_key, timeout=timeout)
    if text and text.strip():
        jina_cache.set(key, text)
    return text
