from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])


class LiteratureExecuteBody(BaseModel):
    message: str
    session_id: str | None = None
    fetch_urls: list[str] | None = None


@router.post("/literature/execute")
async def literature_execute(_body: LiteratureExecuteBody):
    """Deprecated — use POST /api/tasks + GET /api/tasks/{id}/stream instead."""
    raise HTTPException(
        status_code=410,
        detail=(
            "Direct SSE execute is removed. "
            "Create a background task via POST /api/tasks, "
            "then subscribe to GET /api/tasks/{task_id}/stream."
        ),
    )
