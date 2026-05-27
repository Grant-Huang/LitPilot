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
) -> None:
    """Merge Crossref/OpenAlex enrich fields into library upsert patch."""
    if enrich.get("title") and not patch.get("title"):
        patch["title"] = enrich["title"]
    for key in _ENRICH_PATCH_KEYS:
        if key == "title":
            continue
        if enrich.get(key) is None or enrich.get(key) == "":
            continue
        if key == "abstract" and patch.get("abstract"):
            if len(str(enrich["abstract"])) <= len(str(patch["abstract"])):
                continue
        patch[key] = enrich[key]
    resolved = normalize_doi(enrich.get("doi") or rec_doi or patch.get("doi", ""))
    if resolved:
        patch["doi"] = resolved


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
        merged = merge_item(items[item_id], patch)
        if patch.get("doi"):
            merged["doi"] = normalize_doi(str(patch["doi"]))
        items[item_id] = merged
        return merged

    return lib._with_lock(_op)


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
    patch = enrich_patch_from_doi(resolved)
    if not patch:
        return {"ok": False, "error": "crossref_failed"}
    patch["doi"] = resolved
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
