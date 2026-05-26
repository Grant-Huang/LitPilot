from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.response import ok
from app.library.dedupe import dedupe_library
from app.library.enrich import enrich_item_citations
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
    stats = await reconcile_library(
        session_id=body.session_id,
        mode=body.mode,
        jina_api_key=settings.get("jina_api_key") or None,
        timeout=float(settings.get("fetch_timeout_sec") or 45),
        citation_format=str(settings.get("citation_format") or "apa"),
    )
    return ok(stats)


@router.post("/items/{item_id}/enrich")
async def enrich_item(item_id: str):
    result = enrich_item_citations(item_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "enrich failed"))
    return ok(result)


@router.patch("/items/{item_id}/star")
async def star_item(item_id: str, body: StarBody):
    lib = _ensure_library()
    item = lib.set_starred(item_id, body.starred)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return ok({"item": item})


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
