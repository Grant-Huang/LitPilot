"""Apply Crossref + OpenAlex metadata enrichment to library items."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from app.library.crossref import fetch_crossref_work, normalize_doi
from app.library.models import merge_item
from app.library.openalex import lookup_doi_openalex
from app.library.store import LibraryStore
from app.skills.citation_extractor import CitationRecord

_ENRICH_PATCH_KEYS = (
    "authors",
    "year",
    "venue",
    "volume",
    "issue",
    "pages",
    "month",
    "publisher",
    "abstract",
    "citation_count",
    "references_count",
    "references_preview",
    "doi",
    "title",
)

# Crossref / OpenAlex 书目字段优先于页面抓取
_AUTHORITATIVE_BIB_KEYS = frozenset(
    {"title", "authors", "year", "venue", "doi", "volume", "issue", "pages", "month", "publisher"}
)


def _sync_exports(lib: LibraryStore) -> None:
    from app.library.from_run import _sync_exports as sync

    sync(lib)


def resolve_doi_for_record(rec: CitationRecord) -> str:
    """Prefer parsed DOI; otherwise OpenAlex title/author lookup."""
    doi = normalize_doi(rec.doi or "")
    if doi:
        return doi
    if not (rec.title or "").strip():
        return ""
    found = lookup_doi_openalex(
        rec.title,
        rec.authors,
        rec.year,
    )
    if found:
        rec.doi = found
    return found or ""


def crossref_patch_for_doi(doi: str) -> dict[str, Any] | None:
    return fetch_crossref_work(doi)


def enrich_patch_from_doi(doi: str) -> dict[str, Any]:
    patch = fetch_crossref_work(doi) or {}
    if patch.get("doi"):
        patch["doi"] = normalize_doi(str(patch["doi"]))
    return patch


def build_enrich_patch_for_record(rec: CitationRecord) -> dict[str, Any]:
    """Resolve DOI (incl. OpenAlex) then fetch Crossref bibliometrics."""
    doi = resolve_doi_for_record(rec)
    if not doi:
        return {}
    patch = enrich_patch_from_doi(doi)
    return patch


def merge_enrich_into_patch(
    patch: dict[str, Any],
    enrich: dict[str, Any],
    *,
    rec_doi: str = "",
    authoritative: bool = True,
) -> None:
    """Merge Crossref/OpenAlex enrich fields into library upsert patch."""
    if not enrich:
        return
    for key in _ENRICH_PATCH_KEYS:
        val = enrich.get(key)
        if val is None or val == "":
            continue
        if key == "abstract" and patch.get("abstract"):
            if len(str(val)) <= len(str(patch["abstract"])):
                continue
        if key in _AUTHORITATIVE_BIB_KEYS and authoritative:
            patch[key] = val
            continue
        if key == "title" and not patch.get("title"):
            patch["title"] = val
            continue
        if key != "title":
            patch[key] = val
    resolved = normalize_doi(enrich.get("doi") or rec_doi or patch.get("doi", ""))
    if resolved:
        patch["doi"] = resolved


def rebuild_citation_lines(
    patch: dict[str, Any],
    *,
    display_index: int,
    citation_format: str = "apa",
) -> None:
    """Regenerate APA/ACM lines from patch title/authors/year/venue/doi."""
    from app.skills.citation_extractor import CitationFormat, CitationRecord

    authors = patch.get("authors") or []
    if isinstance(authors, list):
        authors_str = ", ".join(str(a) for a in authors if str(a).strip())
    else:
        authors_str = str(authors)
    rec = CitationRecord(
        title=str(patch.get("title") or ""),
        authors=authors_str,
        year=str(patch.get("year") or ""),
        venue=str(patch.get("venue") or ""),
        doi=str(patch.get("doi") or ""),
        url=str(patch.get("url") or ""),
        success=True,
    )
    fmt: CitationFormat = "acm" if citation_format == "acm" else "apa"
    cites = dict(patch.get("citations") or {})
    cites["apa"] = rec.to_apa(display_index)
    cites[fmt] = rec.format_line(display_index, fmt)
    patch["citations"] = cites


async def enrich_records_parallel(
    records: list[CitationRecord],
    *,
    parallel: int = 4,
) -> list[dict[str, Any]]:
    """Batch enrich successful citation records (OpenAlex + Crossref) in parallel."""
    sem = asyncio.Semaphore(max(1, min(parallel, 12)))

    async def _one(rec: CitationRecord) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(build_enrich_patch_for_record, rec)

    return list(await asyncio.gather(*[_one(r) for r in records]))


def apply_metadata_patch(
    lib: LibraryStore,
    item_id: str,
    patch: dict[str, Any],
) -> Optional[dict[str, Any]]:
    if not patch:
        return lib.get_item(item_id)

    def _op(db: dict[str, Any]) -> Optional[dict[str, Any]]:
        items = db["items"]
        if item_id not in items:
            return None
        merged = merge_item(items[item_id], patch, authoritative=True)
        if patch.get("doi"):
            merged["doi"] = normalize_doi(str(patch["doi"]))
        items[item_id] = merged
        return merged

    return lib._with_lock(_op)


def refresh_item_metadata(
    item: dict[str, Any],
    *,
    enrich_patch: dict[str, Any] | None = None,
    citation_format: str = "apa",
) -> dict[str, Any]:
    """Apply authoritative Crossref patch and rebuild citation lines for one item."""
    patch: dict[str, Any] = {
        "title": item.get("title"),
        "authors": item.get("authors"),
        "year": item.get("year"),
        "venue": item.get("venue"),
        "doi": item.get("doi"),
        "url": item.get("url"),
        "publisher": item.get("publisher"),
        "abstract": item.get("abstract"),
        "citations": dict(item.get("citations") or {}),
    }
    ep = enrich_patch if enrich_patch is not None else {}
    if not ep:
        rec = _citation_record_from_item(item)
        ep = build_enrich_patch_for_record(rec)
    merge_enrich_into_patch(patch, ep, rec_doi=str(item.get("doi") or ""))
    idx = int(item.get("display_index") or 0) or 1
    rebuild_citation_lines(patch, display_index=idx, citation_format=citation_format)
    return patch


def _citation_record_from_item(item: dict[str, Any]) -> CitationRecord:
    authors = item.get("authors") or []
    if isinstance(authors, list):
        authors_str = ", ".join(str(a) for a in authors)
    else:
        authors_str = str(authors or "")
    return CitationRecord(
        title=str(item.get("title") or ""),
        authors=authors_str,
        year=str(item.get("year") or ""),
        venue=str(item.get("venue") or ""),
        doi=str(item.get("doi") or ""),
        url=str(item.get("url") or ""),
        abstract=str(item.get("abstract") or ""),
        publisher=str(item.get("publisher") or ""),
        success=True,
    )


async def refresh_library_metadata(
    lib: LibraryStore | None = None,
    *,
    parallel: int = 4,
    citation_format: str = "apa",
    item_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Re-enrich all (or selected) library items from Crossref/OpenAlex."""
    import asyncio

    lib = lib or LibraryStore()
    items = lib.list_items()
    if item_ids:
        wanted = set(item_ids)
        items = [i for i in items if i.get("id") in wanted]

    sem = asyncio.Semaphore(max(1, min(parallel, 12)))
    updated = 0
    skipped = 0

    async def _one(item: dict[str, Any]) -> None:
        nonlocal updated, skipped
        async with sem:
            ep = await asyncio.to_thread(
                build_enrich_patch_for_record,
                _citation_record_from_item(item),
            )
        if not ep:
            skipped += 1
            return
        patch = refresh_item_metadata(
            item,
            enrich_patch=ep,
            citation_format=citation_format,
        )
        result = apply_metadata_patch(lib, str(item["id"]), patch)
        if result:
            updated += 1
        else:
            skipped += 1

    await asyncio.gather(*[_one(i) for i in items])
    if updated:
        _sync_exports(lib)
    return {"updated": updated, "skipped": skipped, "total": len(items)}


def enrich_item_from_crossref(
    item_id: str,
    lib: LibraryStore | None = None,
    *,
    doi: str | None = None,
) -> dict[str, Any]:
    lib = lib or LibraryStore()
    item = lib.get_item(item_id)
    if not item:
        return {"ok": False, "error": "not_found"}
    resolved = normalize_doi(doi or str(item.get("doi") or ""))
    if not resolved:
        resolved = lookup_doi_openalex(
            str(item.get("title") or ""),
            item.get("authors") or [],
            str(item.get("year") or ""),
        )
    if not resolved:
        return {"ok": False, "error": "no_doi"}
    ep = enrich_patch_from_doi(resolved)
    if not ep:
        return {"ok": False, "error": "crossref_failed"}
    ep["doi"] = resolved
    item = lib.get_item(item_id) or {}
    patch = refresh_item_metadata(
        item,
        enrich_patch=ep,
        citation_format="apa",
    )
    updated = apply_metadata_patch(lib, item_id, patch)
    if not updated:
        return {"ok": False, "error": "not_found"}
    _sync_exports(lib)
    return {
        "ok": True,
        "item": updated,
        "citation_count": updated.get("citation_count"),
        "references_count": updated.get("references_count"),
        "doi_resolved": resolved,
    }
