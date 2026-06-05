"""Native web_search via DuckDuckGo HTML (no API key)."""
from __future__ import annotations

import re
from typing import Any

import httpx

from app.agents.tools.web_search_domains import (
    filter_hits_by_domains,
    validate_search_domains,
)

_USER_AGENT = (
    "LitPilot/1.0 (+https://github.com/litpilot; academic literature search)"
)
_DDG_URL = "https://html.duckduckgo.com/html/"
_RESULT_LINK_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
    re.I,
)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>([^<]+)</a?',
    re.I,
)


async def search(
    query: str,
    *,
    max_results: int = 8,
    allowed_domains: list[str] | tuple[str, ...] | None = None,
    blocked_domains: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return standard web_search payload: {results: [{url, title, snippet}], answer}."""
    q = (query or "").strip()
    if len(q) < 2:
        return {"results": [], "answer": ""}

    domain_err = validate_search_domains(allowed_domains, blocked_domains)
    if domain_err:
        raise ValueError(domain_err)

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html",
    }
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        resp = await client.post(
            _DDG_URL,
            data={"q": q, "b": ""},
            headers=headers,
        )
        resp.raise_for_status()
        html = resp.text or ""

    links = _RESULT_LINK_RE.findall(html)
    snippets = _SNIPPET_RE.findall(html)
    rows: list[dict[str, str]] = []
    for i, (url, title) in enumerate(links):
        if not url.startswith("http"):
            continue
        snippet = snippets[i][:800] if i < len(snippets) else ""
        rows.append({
            "url": url.strip(),
            "title": re.sub(r"\s+", " ", title).strip()[:300],
            "snippet": snippet.strip(),
        })

    rows = filter_hits_by_domains(
        rows,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )
    cap = max(1, min(max_results, 25))
    return {"results": rows[:cap], "answer": ""}
