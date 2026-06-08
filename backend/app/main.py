import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, library, sessions, settings, tasks
from app.core.response import err, ok

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")
api_router.include_router(sessions.router)
api_router.include_router(settings.router)
api_router.include_router(library.router)
api_router.include_router(chat.router)
api_router.include_router(tasks.router)


def _health_payload() -> dict:
    return ok({"service": "litpilot"})


@api_router.get("/health")
async def api_health():
    """与 /api/* 同前缀的健康检查。"""
    return _health_payload()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """启动 / 关闭钩子（替代已弃用的 on_event）。

    关键修复：
    - 先启动 task sweeper，即便日志读取失败也不会卡住后续接口；
    - 配置读取放到线程池避免阻塞事件循环；
    - 全程 try/except 保证启动幂等，异常仅记录日志。
    """
    import asyncio

    from app.core.config import DATA_DIR
    from app.llm.http_client import aclose_all
    from app.storage.file_store import get_store
    from app.tasks.literature_tasks import start_task_sweeper, stop_task_sweeper

    try:
        await start_task_sweeper()
    except Exception:
        logger.exception("lifespan: start_task_sweeper failed")

    try:
        merged = await asyncio.to_thread(get_store().get_agent_settings_merged)
        logger.info(
            "LitPilot data_dir=%s fetch_provider=%s max_fetch_urls=%s",
            DATA_DIR,
            merged.get("fetch_provider"),
            merged.get("max_fetch_urls"),
        )
    except Exception:
        logger.exception("lifespan: failed to load agent settings at startup")

    try:
        yield
    finally:
        try:
            await stop_task_sweeper()
        except Exception:
            logger.exception("lifespan: stop_task_sweeper failed")
        try:
            await aclose_all()
        except Exception:
            logger.exception("lifespan: aclose_all failed")


app = FastAPI(
    title="LitPilot API",
    description="Literature review assistant for researchers",
    version="0.1.0",
    redirect_slashes=False,
    lifespan=_lifespan,
)

def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """根路径：避免误访问 / 时看到 Not Found。"""
    return _health_payload()


@app.get("/health")
@app.get("/health/")
async def health():
    return _health_payload()


app.include_router(api_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(status_code=422, content=err("Validation error", exc.errors()))
