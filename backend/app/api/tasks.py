import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.response import err, ok
from app.storage.file_store import get_store
from app.tasks.literature_tasks import get_task_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskBody(BaseModel):
    session_id: Optional[str] = None
    message: str
    fetch_urls: Optional[list[str]] = None


@router.post("")
async def create_task(body: CreateTaskBody):
    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    store = get_store()
    session_id = (body.session_id or "").strip() or None
    if session_id:
        if not store.get_session(session_id):
            raise HTTPException(status_code=404, detail="session not found")
    else:
        meta = store.create_session(title="新综述")
        session_id = meta["id"]

    registry = get_task_registry()
    task = await registry.create_and_start(
        session_id=session_id,
        message=text,
        fetch_urls=body.fetch_urls,
    )
    return ok(task.to_status_dict())


@router.get("/active")
async def list_active_tasks():
    registry = get_task_registry()
    items = [t.to_active_dict() for t in registry.list_active()]
    return ok({"items": items})


@router.get("/{task_id}/status")
async def get_task_status(task_id: str):
    registry = get_task_registry()
    task = registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return ok(task.to_status_dict())


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    registry = get_task_registry()
    try:
        task = await registry.cancel(task_id)
    except Exception:
        logger.exception("cancel_task: unhandled error for %s", task_id)
        raise HTTPException(status_code=500, detail="取消任务失败，请重试")
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return ok(task.to_status_dict())


@router.get("/{task_id}/stream")
async def stream_task(
    task_id: str,
    since: int = Query(0, ge=0),
):
    registry = get_task_registry()
    task = registry.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    async def generate():
        async for line in registry.iter_stream(task_id, since=since):
            yield line

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
