"""Normalize academic source rows to web_search hit shape."""
from __future__ import annotations

from typing import Any


def hit(
    *,
    url: str,
    title: str,
    snippet: str = "",
    source: str = "",
) -> dict[str, str]:
    row: dict[str, str] = {
        "url": url.strip(),
        "title": (title or "").strip()[:300],
        "snippet": (snippet or "").strip()[:800],
    }
    if source:
        row["source"] = source
    return row


def merge_snippet(*parts: str) -> str:
    bits = [p.strip() for p in parts if p and p.strip()]
    return " · ".join(bits)[:800]
