from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.response import ok
from app.library.crossref import normalize_doi
from app.library.dedupe import dedupe_library
from app.library.enrich import enrich_item_citations
from app.library.metadata_enrich import enrich_item_from_crossref, refresh_library_metadata
from app.library.migrate import migrate_legacy_refs
from app.library.reconcile import reconcile_library
from app.library.store import LibraryStore
from app.storage.file_store import get_store

router = APIRouter(prefix="/library", tags=["library"])


class ReconcileBody(BaseModel):
    session_id: Optional[str] = None
    mode: Literal["session", "all", "failed_only"] = "session"


class StarBody(BaseModel):
    starred: bool = True


class TagsBody(BaseModel):
    tags: list[str] = []


class RefreshMetadataBody(BaseModel):
    item_ids: Optional[list[str]] = None
    parallel: int = Field(default=4, ge=1, le=12)


class MetadataBody(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    year: Optional[str] = None
    venue: Optional[str] = None
    doi: Optional[str] = None
    publisher: Optional[str] = None
    abstract: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    month: Optional[str] = None
    refresh_crossref: bool = Field(
        default=True,
        description="DOI 变更或补全时是否从 Crossref 拉取被引/他引与书目",
    )


def _ensure_library() -> LibraryStore:
    lib = LibraryStore()
    if lib.list_items():
        return lib
    legacy = get_store().load_ref_index().get("refs") or []
    if legacy:
        migrate_legacy_refs(lib)
        dedupe_library(lib)
    return lib


@router.get("/items")
async def list_library_items():
    lib = _ensure_library()
    return ok({"items": lib.list_items(), "total": len(lib.list_items())})


@router.get("/items/{item_id}")
async def get_library_item(item_id: str):
    lib = _ensure_library()
    item = lib.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    full_text = lib.read_full_text(item_id)
    return ok({"item": item, "full_text": full_text})


@router.get("/refs")
async def list_refs():
    """Legacy + library merged response for gradual frontend migration."""
    lib = _ensure_library()
    return ok({
        "index": lib.sync_legacy_index(),
        "ref_list_text": lib.export_ref_list_text(),
        "items": lib.list_items(),
    })


@router.post("/migrate")
async def migrate_refs():
    stats = migrate_legacy_refs()
    return ok(stats)


@router.post("/dedupe")
async def dedupe_refs():
    stats = dedupe_library()
    return ok(stats)


@router.post("/reconcile")
async def reconcile_refs(body: ReconcileBody):
    settings = get_store().get_agent_settings_merged()
    fetch_provider = str(settings.get("fetch_provider") or "native").strip().lower()
    fetch_api_key = (
        str(settings.get("fetch_api_key") or "").strip()
        if fetch_provider == "jina"
        else None
    )
    stats = await reconcile_library(
        session_id=body.session_id,
        mode=body.mode,
        fetch_api_key=fetch_api_key or None,
        timeout=float(settings.get("fetch_timeout_sec") or 45),
        citation_format=str(settings.get("citation_format") or "apa"),
    )
    return ok(stats)


@router.post("/refresh-metadata")
async def refresh_all_metadata(body: RefreshMetadataBody | None = None):
    """按 Crossref/OpenAlex 重新拉取书目与被引数，覆盖库内已有字段。"""
    lib = _ensure_library()
    settings = get_store().get_agent_settings_merged()
    body = body or RefreshMetadataBody()
    stats = await refresh_library_metadata(
        lib,
        parallel=body.parallel,
        citation_format=str(settings.get("citation_format") or "apa"),
        item_ids=body.item_ids,
    )
    return ok(stats)


@router.post("/items/{item_id}/enrich")
async def enrich_item(item_id: str):
    result = enrich_item_citations(item_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "enrich failed"))
    return ok(result)


@router.patch("/items/{item_id}/metadata")
async def patch_item_metadata(item_id: str, body: MetadataBody):
    lib = _ensure_library()
    item = lib.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    patch = body.model_dump(exclude={"refresh_crossref"}, exclude_none=True)
    doi_in = patch.pop("doi", None)
    force_doi = doi_in is not None
    if doi_in is not None:
        patch["doi"] = normalize_doi(doi_in)

    updated = lib.patch_item_metadata(item_id, patch, force_doi=force_doi)
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.refresh_crossref and (updated.get("doi") or doi_in):
        result = enrich_item_from_crossref(item_id, lib, doi=updated.get("doi"))
        if result.get("ok"):
            updated = result.get("item") or updated

    return ok({"item": updated})


@router.patch("/items/{item_id}/star")
async def star_item(item_id: str, body: StarBody):
    lib = _ensure_library()
    item = lib.set_starred(item_id, body.starred)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return ok({"item": item})


@router.patch("/items/{item_id}/tags")
async def update_item_tags(item_id: str, body: TagsBody):
    lib = _ensure_library()
    item = lib.set_tags(item_id, body.tags)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return ok({"item": item})


@router.get("/tags")
async def list_library_tags():
    lib = _ensure_library()
    return ok({"tags": lib.list_tags()})


@router.delete("/items/{item_id}")
async def delete_library_item(item_id: str):
    lib = _ensure_library()
    if not lib.delete_item(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    from app.library.from_run import _sync_exports

    _sync_exports(lib)
    return ok({"deleted": True, "item_id": item_id})


@router.delete("/items")
async def clear_library_items():
    """清空全局文献库（不可恢复）。"""
    lib = _ensure_library()
    removed = lib.clear_all()
    from app.library.from_run import _sync_exports

    _sync_exports(lib)
    return ok({"cleared": removed})


@router.get("/items/{item_id}/related-sessions")
async def related_sessions(item_id: str):
    lib = _ensure_library()
    item = lib.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    store = get_store()
    seen: set[str] = set()
    sessions: list[dict[str, Any]] = []
    for prov in item.get("provenance") or []:
        sid = str(prov.get("session_id") or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        meta = store.get_session(sid) or {}
        title = (
            str(prov.get("session_title") or "").strip()
            or str(meta.get("title") or "").strip()
            or sid
        )
        sessions.append({
            "session_id": sid,
            "session_title": title,
            "first_question": store.load_first_user_message(sid),
            "review_ref_index": prov.get("review_ref_index"),
        })
    return ok({"sessions": sessions})


@router.get("/pdfs")
async def list_pdfs():
    return ok({"files": get_store().list_pdfs()})


@router.get("/pdfs/{filename}")
async def get_pdf(filename: str):
    path = get_store().pdf_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.get("/sources/{item_id}")
async def get_source_markdown(item_id: str):
    lib = _ensure_library()
    text = lib.read_full_text(item_id)
    if not text:
        raise HTTPException(status_code=404, detail="Full text not found")
    return ok({"item_id": item_id, "content": text})
