"""Literature intent router — session title + search query via LLM JSON."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.llm_json import parse_json_object
from app.llm.base import LLMMessage
from app.services.llm_service import get_llm
from app.storage.file_store import is_default_session_title

ROUTER_SYSTEM = """你是文献综述助手的路由器。根据用户首条研究问题，输出唯一 JSON（无 markdown 代码块）：
{
  "session_title": "简短会话标题，8-24 字，概括研究主题，不用引号，禁止「新综述」「文献综述」等泛称",
  "search_query": "用于学术检索的精炼查询（≤120 字，可中英）"
}
search_query 规则：
- 聚焦研究对象与领域（方法、系统、架构），不要写成「如何写综述」「AI 写文献」等教程类检索。
- 若用户指制造领域的 MOM/MES，必须写清 manufacturing operations management / 制造运营 / MES，禁止与 ML 领域的 Mixture-of-Memories 混淆。
- 优先 peer-reviewed paper、survey、systematic review 等学术表述；不要复述用户整段提纲。
仅输出 JSON。"""

SEARCH_QUERY_MAX = 200
TOPIC_LABEL_MAX = 120


@dataclass
class LiteratureRouterResult:
    session_title: str
    search_query: str


def clamp_search_query(
    text: str,
    *,
    max_len: int = SEARCH_QUERY_MAX,
    fallback: str = "",
) -> str:
    q = str(text or "").strip()[:max_len]
    if q:
        return q
    fb = str(fallback or "").strip()[:max_len]
    return fb


def parse_router_json(raw: str) -> dict[str, Any]:
    return parse_json_object(raw)


# Backward-compatible aliases for internal imports
_parse_router_json = parse_router_json


def fallback_session_title(user_message: str) -> str:
    t = user_message.strip().replace("\n", " ")
    if not t:
        return "新综述"
    return t[:40] + ("…" if len(t) > 40 else "")


_fallback_title = fallback_session_title


def sanitize_session_title(title: str, user_message: str) -> str:
    t = (title or "").strip().strip("\"'「」『』")
    if not t or is_default_session_title(t):
        return fallback_session_title(user_message)
    return t[:80]


_sanitize_session_title = sanitize_session_title


def fallback_router_result(user_message: str) -> LiteratureRouterResult:
    msg = user_message.strip()
    return LiteratureRouterResult(
        session_title=fallback_session_title(msg),
        search_query=clamp_search_query(msg, fallback=msg),
    )


def build_router_result(data: dict[str, Any], user_message: str) -> LiteratureRouterResult:
    msg = user_message.strip()
    fallback_q = clamp_search_query(msg, fallback=msg)
    title = sanitize_session_title(str(data.get("session_title") or ""), msg)
    search_query = clamp_search_query(
        str(data.get("search_query") or msg),
        fallback=fallback_q,
    )
    return LiteratureRouterResult(session_title=title, search_query=search_query)


async def route_literature(user_message: str) -> LiteratureRouterResult:
    """LLM router for session title and search query; rule-based fallback."""
    msg = user_message.strip()
    fallback = fallback_router_result(msg)
    if not msg:
        return fallback
    try:
        llm = await get_llm()
        resp = await llm.chat(
            [LLMMessage(role="user", content=msg[:800])],
            system=ROUTER_SYSTEM,
            max_tokens=200,
            temperature=0.0,
        )
        data = parse_router_json(resp.content or "")
        return build_router_result(data, msg)
    except Exception:
        return fallback


def should_auto_rename_session(
    meta: dict[str, Any] | None,
    user_message: str,
    *,
    user_message_count: int,
) -> bool:
    """仅首轮用户消息后自动改标题一次；之后不再改（用户可手动改名）。"""
    if not meta or user_message_count != 1:
        return False
    if meta.get("title_auto_set"):
        return False
    if not user_message.strip():
        return False
    title = (meta.get("title") or "").strip()
    if is_default_session_title(title):
        return True
    prefix = user_message.strip()[:40]
    return bool(prefix and title == prefix)
