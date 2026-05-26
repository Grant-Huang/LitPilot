from __future__ import annotations

import httpx


async def jina_fetch(
    url: str,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> str:
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"

    headers: dict[str, str] = {"Accept": "text/markdown"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    reader_url = f"https://r.jina.ai/{target}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(reader_url, headers=headers)
        resp.raise_for_status()
        text = resp.text or ""
        return text[:120_000]
