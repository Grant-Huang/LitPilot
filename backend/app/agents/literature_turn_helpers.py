"""Small pure helpers for literature turn orchestration."""
from __future__ import annotations

import uuid
from typing import Any

from app.agents.literature_intent import LiteratureIntentResult
from app.agents.literature_router import LiteratureRouterResult
from app.agents.research_decompose import extract_compact_base_query
from app.agents.tools.tavily_search import augment_literature_search_query
from app.schemas.literature_outline import LiteratureOutline


def section_specs_for_graph(outline: LiteratureOutline) -> list[tuple[str, str]]:
    return [(s.id, s.title) for s in outline.sections]


def resolve_search_queries(
    intent: LiteratureIntentResult,
    router_result: LiteratureRouterResult,
    route_message: str,
) -> tuple[str, str]:
    raw_base = (
        intent.search_query
        or router_result.search_query.strip()
        or route_message.strip()
    )
    base_query = extract_compact_base_query(raw_base) or raw_base.strip()[:120]
    return base_query, augment_literature_search_query(base_query)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def augment_query(query: str) -> str:
    return augment_literature_search_query(query)


def last_assistant_failed(msgs: list[dict[str, Any]]) -> list[dict[str, str]]:
    for msg in reversed(msgs):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("meta") or {}
        failed = meta.get("failed_literature") or []
        if failed:
            return [dict(f) for f in failed]
    return []


def intent_needs_tavily(intent: LiteratureIntentResult) -> bool:
    if intent.intent in ("query_corpus", "manage_library", "refine_gen", "regen_only"):
        return False
    if intent.skip_tavily:
        return False
    return intent.intent in (
        "new_topic",
        "expand_search",
        "supplement",
        "synthesis_matrix",
    )
