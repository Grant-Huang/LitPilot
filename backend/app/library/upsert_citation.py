"""Upsert library items from CitationRecord."""
from __future__ import annotations

from typing import Any, Optional

from app.library.metadata_enrich import build_enrich_patch_for_record, merge_enrich_into_patch
from app.library.models import merge_item, parse_authors, provenance_entry
from app.library.store import LibraryStore
from app.skills.citation_extractor import CitationFormat, CitationRecord


def upsert_from_citation(
    rec: CitationRecord,
    *,
    lib: LibraryStore | None = None,
    citation_format: CitationFormat = "apa",
    session_id: str = "",
    session_title: str = "",
    display_index_hint: int | None = None,
    enrich_patch: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    lib = lib or LibraryStore()
    url = rec.url or ""
    if not url:
        return None

    prov = []
    if session_id:
        prov.append(
            provenance_entry(
                session_id,
                "cite_extract",
                session_title=session_title,
            )
        )

    if rec.success:
        idx = display_index_hint or _next_display_for_cite(lib, rec)
        cite_line = rec.format_line(idx, citation_format)
        patch: dict[str, Any] = {
            "title": rec.title,
            "authors": parse_authors(rec.authors),
            "year": rec.year,
            "venue": rec.venue,
            "url": url,
            "doi": rec.doi,
            "publisher": rec.publisher,
            "abstract": rec.abstract,
            "citations": {citation_format: cite_line, "apa": rec.to_apa(idx)},
            "provenance": prov,
            "availability": {
                "cite_status": "ok",
                "has_abstract": bool(rec.abstract),
                "fetch_status": "ok",
            },
        }
        cr = enrich_patch if enrich_patch is not None else build_enrich_patch_for_record(rec)
        if cr:
            merge_enrich_into_patch(patch, cr, rec_doi=rec.doi or "")
        item = lib.upsert(patch, url=url, doi=patch.get("doi") or rec.doi or "")
        lib._with_lock(
            lambda db: _set_display_index(db, item["id"], idx) or {}
        )
        return lib.get_item(item["id"])

    patch = {
        "title": rec.title or url,
        "url": url,
        "provenance": prov,
        "availability": {
            "cite_status": "failed",
            "fetch_status": "pending",
        },
    }
    return lib.upsert(patch, url=url, doi=rec.doi)


def _next_display_for_cite(lib: LibraryStore, rec: CitationRecord) -> int:
    existing = lib.find_by_url_or_doi(url=rec.url, doi=rec.doi)
    if existing and existing.get("display_index"):
        return int(existing["display_index"])
    db = lib._read_db()
    return int(db.get("next_display_index") or 0) + 1


def _set_display_index(db: dict[str, Any], item_id: str, idx: int) -> None:
    items = db["items"]
    item = items[item_id]
    item["display_index"] = idx
    db["next_display_index"] = max(int(db.get("next_display_index") or 0), idx)
    apa = (item.get("citations") or {}).get("apa") or ""
    if apa and f"[{idx}]" not in apa[:8]:
        rec = CitationRecord(
            title=item.get("title", ""),
            authors=", ".join(item.get("authors") or []),
            year=str(item.get("year") or ""),
            venue=item.get("venue", ""),
            doi=item.get("doi", ""),
            url=item.get("url", ""),
            success=True,
        )
        item["citations"]["apa"] = rec.to_apa(idx)
        fmt = item.get("citations", {}).get("acm")
        if fmt:
            item["citations"]["acm"] = rec.to_acm(idx)
