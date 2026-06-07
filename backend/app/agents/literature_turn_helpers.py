"""Small pure helpers for literature turn orchestration."""
from __future__ import annotations

import uuid
from typing import Any

from app.agents.intent_policy import runs_search
from app.agents.literature_intent import LiteratureIntentResult
from app.agents.literature_router import LiteratureRouterResult
from app.agents.research_decompose import extract_compact_base_query
from app.schemas.literature_outline import LiteratureOutline


def section_specs_for_graph(outline: LiteratureOutline) -> list[tuple[str, str]]:
    return [(s.id, s.title) for s in outline.sections]


def resolve_search_queries(
    intent: LiteratureIntentResult,
    router_result: LiteratureRouterResult,
    route_message: str,
) -> tuple[str, str]:
    raw_base = (
        router_result.search_query.strip()
        or route_message.strip()
    )
    base_query = extract_compact_base_query(raw_base) or raw_base.strip()[:120]
    return base_query, base_query


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def last_assistant_failed(msgs: list[dict[str, Any]]) -> list[dict[str, str]]:
    for msg in reversed(msgs):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("meta") or {}
        failed = meta.get("failed_literature") or []
        if failed:
            return [dict(f) for f in failed]
    return []


def intent_needs_web_search(intent: LiteratureIntentResult) -> bool:
    return runs_search(intent)
