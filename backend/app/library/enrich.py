"""Optional metadata enrichment (Crossref)."""
from __future__ import annotations

from typing import Any

from app.library.metadata_enrich import enrich_item_from_crossref
from app.library.store import LibraryStore


def enrich_item_citations(item_id: str, lib: LibraryStore | None = None) -> dict[str, Any]:
    """Refresh 被引/他引与书目字段 from Crossref (requires DOI)."""
    return enrich_item_from_crossref(item_id, lib)
