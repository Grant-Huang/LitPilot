from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.literature_workflow import stream_literature_turn
from app.agents.agent_skills import capabilities_payload
from app.core.streaming import normalize_chat_event, sse_event
from app.storage.file_store import get_store

router = APIRouter(prefix="/chat", tags=["chat"])


class LiteratureExecuteBody(BaseModel):
    message: str
    session_id: Optional[str] = None
    fetch_urls: Optional[list[str]] = None


@router.post("/literature/execute")
async def literature_execute(body: LiteratureExecuteBody):
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

    async def generate():
        yield sse_event(
            "extension",
            {"name": "session", "version": "1.0", "data": {"session_id": session_id}},
        )
        yield sse_event("capabilities", capabilities_payload())
        try:
            async for ev_type, payload in stream_literature_turn(
                session_id,
                text,
                extra_fetch_urls=body.fetch_urls,
            ):
                for norm_type, norm_payload in normalize_chat_event(ev_type, payload):
                    yield sse_event(norm_type, norm_payload)
            yield sse_event("done", {})
        except ValueError as e:
            yield sse_event("error", {"message": str(e)})
            yield sse_event("done", {})
        except Exception as e:
            yield sse_event("error", {"message": f"Error: {e}"})
            yield sse_event("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
