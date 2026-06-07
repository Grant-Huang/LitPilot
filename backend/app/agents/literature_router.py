"""Literature intent router — session title + search query via LLM JSON."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.agents.llm_json import parse_json_object
from app.agents.prompt_registry import DEFAULT_ROUTER_SYSTEM as ROUTER_SYSTEM
from app.agents.prompt_settings import get_router_system_prompt
from app.agents.search_query_utils import (
    SEARCH_QUERY_MAX,
    TOPIC_LABEL_MAX,
    clamp_search_query,
)
from app.llm.base import LLMMessage
from app.services.llm_service import get_router_llm
from app.storage.file_store import is_default_session_title

if TYPE_CHECKING:
    from app.agents.search_aspects import SearchAspect

FOCUS_MAX = 300


@dataclass
class LiteratureRouterResult:
    session_title: str
    search_query: str
    needs_clarification: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    narration_focus: str = ""
    writing_emphasis: str = ""
    search_aspects: list[SearchAspect] = field(default_factory=list)


# Re-export for backward-compatible imports from literature_router.
__all__ = [
    "FOCUS_MAX",
    "LiteratureRouterResult",
    "SEARCH_QUERY_MAX",
    "TOPIC_LABEL_MAX",
    "build_router_result",
    "clamp_search_query",
    "fallback_router_result",
    "fallback_session_title",
    "parse_router_json",
    "refine_router_session_title",
    "resolve_auto_session_title",
    "route_literature",
    "sanitize_session_title",
    "should_auto_rename_session",
    "title_is_message_truncation",
]


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


def title_is_message_truncation(title: str, user_message: str) -> bool:
    """True when title is the rule-based truncation of the user message, not an LLM summary."""
    msg = user_message.strip().replace("\n", " ")
    raw = (title or "").strip()
    if not raw or not msg:
        return False
    fb = fallback_session_title(msg)
    if raw == fb.strip():
        return True
    prefix = msg[:40].rstrip()
    return raw == prefix or raw == prefix + "…"


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
    from app.agents.search_aspects import parse_search_aspects

    msg = user_message.strip()
    fallback_q = clamp_search_query(msg, fallback=msg)
    title = sanitize_session_title(str(data.get("session_title") or ""), msg)
    search_query = clamp_search_query(
        str(data.get("search_query") or msg),
        fallback=fallback_q,
    )
    needs_raw = data.get("needs_clarification")
    needs_clarification = bool(needs_raw) if needs_raw is not None else False
    questions = [
        str(q).strip()
        for q in (data.get("clarification_questions") or [])
        if str(q).strip()
    ]
    aspects = parse_search_aspects(data.get("search_aspects"))
    primary_q = search_query
    if aspects and not primary_q:
        primary_q = aspects[0].primary_query()
    return LiteratureRouterResult(
        session_title=title,
        search_query=primary_q or search_query,
        needs_clarification=needs_clarification,
        clarification_questions=questions[:6],
        narration_focus=str(data.get("narration_focus") or "").strip()[:FOCUS_MAX],
        writing_emphasis=str(data.get("writing_emphasis") or "").strip()[:FOCUS_MAX],
        search_aspects=aspects,
    )


async def route_literature(user_message: str) -> LiteratureRouterResult:
    """LLM router for session title and search query; rule-based fallback."""
    msg = user_message.strip()
    fallback = fallback_router_result(msg)
    if not msg:
        return fallback
    try:
        llm = await get_router_llm()
        router_system = await get_router_system_prompt()
        resp = await llm.chat(
            [LLMMessage(role="user", content=msg[:800])],
            system=router_system,
            max_tokens=200,
            temperature=0.0,
        )
        data = parse_router_json(resp.content or "")
        return build_router_result(data, msg)
    except Exception:
        return fallback


async def refine_router_session_title(
    result: LiteratureRouterResult,
    user_message: str,
) -> LiteratureRouterResult:
    """When orchestrator output lacks JSON, call dedicated router for a real summary title."""
    msg = user_message.strip()
    if not msg or not title_is_message_truncation(result.session_title, msg):
        return result
    routed = await route_literature(msg)
    if title_is_message_truncation(routed.session_title, msg):
        return result
    return LiteratureRouterResult(
        session_title=routed.session_title,
        search_query=routed.search_query or result.search_query,
        needs_clarification=result.needs_clarification,
        clarification_questions=list(result.clarification_questions),
        narration_focus=result.narration_focus or routed.narration_focus,
        writing_emphasis=result.writing_emphasis or routed.writing_emphasis,
        search_aspects=result.search_aspects or routed.search_aspects,
    )


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
    return title_is_message_truncation(title, user_message)


async def resolve_auto_session_title(
    *,
    primary_title: str,
    user_message: str,
) -> str:
    """Resolve a summary title for first-turn auto-rename (never keep default 新综述)."""
    msg = user_message.strip()
    if not msg:
        return ""

    def _usable(title: str) -> bool:
        t = (title or "").strip()
        return bool(t) and not is_default_session_title(t) and not title_is_message_truncation(t, msg)

    candidate = (primary_title or "").strip()
    if _usable(candidate):
        return candidate[:80]

    try:
        routed = await route_literature(msg)
        candidate = (routed.session_title or "").strip()
    except Exception:
        candidate = ""

    if _usable(candidate):
        return candidate[:80]

    fb = fallback_session_title(msg)
    return fb[:80] if not is_default_session_title(fb) else ""
