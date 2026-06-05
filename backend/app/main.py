import logging
import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, library, sessions, settings
from app.core.response import err, ok

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")
api_router.include_router(sessions.router)
api_router.include_router(settings.router)
api_router.include_router(library.router)
api_router.include_router(chat.router)


def _health_payload() -> dict:
    return ok({"service": "litpilot"})


@api_router.get("/health")
async def api_health():
    """与 /api/* 同前缀的健康检查。"""
    return _health_payload()


app = FastAPI(
    title="LitPilot API",
    description="Literature review assistant for researchers",
    version="0.1.0",
    redirect_slashes=False,
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
