"""Expand literature search queries (SurveyX-style keyword broadening, lite)."""
from __future__ import annotations

import json
import logging
import re

from app.agents.prompt_registry import DEFAULT_EXPANSION_SYSTEM as _EXPANSION_SYSTEM
from app.agents.prompt_settings import get_search_expansion_system_prompt
from app.llm.base import LLMMessage

_log = logging.getLogger(__name__)

def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = re.sub(r"\s+", " ", q.strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q.strip())
    return out


def expand_search_queries_rule(base_query: str, *, count: int = 3) -> list[str]:
    base = (base_query or "").strip()
    if not base:
        return []
    cap = max(1, min(int(count or 1), 4))
    queries = [base]
    lower = base.lower()
    if cap >= 2 and "survey" not in lower and "review" not in lower:
        queries.append(f"{base} survey systematic review")
    if cap >= 3 and "state of the art" not in lower and "sota" not in lower:
        queries.append(f"{base} state of the art recent advances")
    if cap >= 4 and "arxiv" not in lower:
        queries.append(f"{base} arxiv")
    return _dedupe_queries(queries)[:cap]


def _parse_query_list(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return []


async def expand_search_queries(
    base_query: str,
    *,
    count: int = 3,
    user_message: str = "",
    llm=None,
    use_llm: bool = True,
) -> list[str]:
    """Return deduped query list; first item is always the base query."""
    base = (base_query or "").strip()
    cap = max(1, min(int(count or 1), 4))
    if cap <= 1 or not base:
        return [base] if base else []

    if use_llm and llm is not None:
        prompt = f"研究主题：{user_message or base}\n基准检索式：{base}\n请输出 {cap} 个检索式 JSON 数组。"
        try:
            expansion_system = await get_search_expansion_system_prompt()
            resp = await llm.chat(
                [LLMMessage(role="user", content=prompt)],
                system=expansion_system,
                max_tokens=280,
                temperature=0.3,
            )
            expanded = _parse_query_list(resp.content or "")
            if expanded:
                if base not in expanded:
                    expanded.insert(0, base)
                return _dedupe_queries(expanded)[:cap]
        except Exception:
            _log.exception("LLM search expansion failed; using rule fallback")

    return expand_search_queries_rule(base, count=cap)
