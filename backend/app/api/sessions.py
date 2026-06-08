from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.response import err, ok
from app.storage.file_store import get_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionBody(BaseModel):
    title: str = "新综述"


class UpdateSessionBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None


# 所有 handler 都是同步文件 I/O，声明为 def 走 FastAPI 线程池，避免占用事件循环。
@router.get("")
def list_sessions():
    return ok(get_store().list_sessions())


@router.post("")
def create_session(body: CreateSessionBody):
    meta = get_store().create_session(title=body.title)
    return ok(meta)


@router.get("/{session_id}")
def get_session(session_id: str):
    meta = get_store().get_session(session_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")
    return ok(meta)


@router.patch("/{session_id}")
def update_session(session_id: str, body: UpdateSessionBody):
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
def delete_session(session_id: str):
    # 删除不存在的 session 必须显式 404，避免掩盖客户端 bug / 重放。
    if not get_store().delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return ok({"deleted": session_id})


@router.get("/{session_id}/messages")
def get_messages(
    session_id: str,
    # limit 必须有上界，否则攻击者一行就能让存储层加载巨量 JSON。
    limit: int = Query(50, ge=1, le=500),
):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return ok(get_store().load_messages(session_id, limit=limit))


@router.get("/{session_id}/review")
def get_session_review(session_id: str):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    review = get_store().get_latest_review(session_id)
    if not review:
        return ok(None)
    return ok(review)


@router.get("/{session_id}/review/{filename}")
def get_session_review_version(session_id: str, filename: str):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    review = get_store().get_review_by_filename(session_id, filename)
    if not review:
        raise HTTPException(status_code=404, detail="Review version not found")
    return ok(review)


@router.get("/{session_id}/matrix")
def get_session_matrix(session_id: str):
    if not get_store().get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    matrix = get_store().get_latest_matrix(session_id)
    if not matrix:
        return ok(None)
    return ok(matrix)
