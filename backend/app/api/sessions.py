from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.response import err, ok
from app.storage.file_store import get_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionBody(BaseModel):
    title: str = "新综述"


class UpdateSessionBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None


@router.get("")
async def list_sessions():
    return ok(get_store().list_sessions())


@router.post("")
async def create_session(body: CreateSessionBody):
    meta = get_store().create_session(title=body.title)
    return ok(meta)


@router.get("/{session_id}")
async def get_session(session_id: str):
    meta = get_store().get_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")
    return ok(meta)


@router.patch("/{session_id}")
async def update_session(session_id: str, body: UpdateSessionBody):
    if body.title is None and body.pinned is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    meta = get_store().update_session(
        session_id,
        title=body.title,
        pinned=body.pinned,
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")
    return ok(meta)


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    get_store().delete_session(session_id)
    return ok({"deleted": session_id})


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, limit: int = 50):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return ok(get_store().load_messages(session_id, limit=limit))


@router.get("/{session_id}/review")
async def get_session_review(session_id: str):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    review = get_store().get_latest_review(session_id)
    if not review:
        return ok(None)
    return ok(review)
