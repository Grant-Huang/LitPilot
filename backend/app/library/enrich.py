"""Optional metadata enrichment (Crossref)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from app.library.store import LibraryStore
from app.library.from_run import _sync_exports


def enrich_item_citations(item_id: str, lib: LibraryStore | None = None) -> dict[str, Any]:
    lib = lib or LibraryStore()
    item = lib.get_item(item_id)
    if not item:
        return {"ok": False, "error": "not_found"}
    doi = (item.get("doi") or "").strip()
    if not doi:
        return {"ok": False, "error": "no_doi"}
    count = _crossref_citation_count(doi)
    if count is None:
        return {"ok": False, "error": "crossref_failed"}

    def _op(db: dict[str, Any]) -> dict[str, Any]:
        from app.library.models import merge_item

        items = db["items"]
        items[item_id] = merge_item(
            items[item_id],
            {"citation_count": count},
        )
        return items[item_id]

    updated = lib._with_lock(_op)
    _sync_exports(lib)
    return {"ok": True, "citation_count": count, "item": updated}


def _crossref_citation_count(doi: str) -> int | None:
    d = doi.strip().rstrip(".")
    url = f"https://api.crossref.org/works/{urllib.parse.quote(d)}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
        msg = data.get("message") or {}
        return int(msg.get("is-referenced-by-count") or 0)
    except Exception:
        return None

