"""LLM-based literature search query refinement (domain disambiguation, generic)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.llm_json import parse_json_object
from app.agents.prompt_registry import DEFAULT_REFINER_SYSTEM as REFINER_SYSTEM
from app.agents.prompt_settings import get_search_refiner_system_prompt
from app.agents.literature_router import SEARCH_QUERY_MAX, clamp_search_query
from app.llm.base import LLMMessage

_log = logging.getLogger(__name__)

_ACADEMIC_MARKERS = (
    "survey",
    "systematic review",
    "literature review",
    "peer-reviewed",
    "peer reviewed",
    "综述",
    "arxiv",
    "doi",
    "paper",
    "论文",
)


@dataclass
class SearchQueryRefinement:
    queries: list[str]
    exclude_title_substrings: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "queries": list(self.queries),
            "exclude_title_substrings": list(self.exclude_title_substrings),
            "clarification_questions": list(self.clarification_questions),
        }


def apply_academic_search_suffix(query: str) -> str:
    """Rule fallback: append academic intent when LLM unavailable."""
    q = (query or "").strip()
    if not q:
        return q
    lower = q.lower()
    if not any(x in lower for x in _ACADEMIC_MARKERS):
        q = f"{q} academic survey peer-reviewed"
    return q[:500]


def _normalize_queries(draft: list[str]) -> list[str]:
    out: list[str] = []
    for q in draft:
        text = clamp_search_query(q, max_len=SEARCH_QUERY_MAX, fallback=q)
        if text:
            out.append(text)
    return out


def _normalize_exclusions(raw: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s[:120])
    return out[:12]


def _normalize_questions(raw: list) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip()
        if s:
            out.append(s[:300])
    return out[:3]


def refine_search_queries_rule(
    draft_queries: list[str],
    *,
    user_message: str = "",
) -> SearchQueryRefinement:
    """Deterministic fallback when LLM refine fails."""
    _ = user_message
    queries = [apply_academic_search_suffix(q) for q in _normalize_queries(draft_queries)]
    return SearchQueryRefinement(queries=queries)


def _align_query_count(refined: list[str], draft: list[str]) -> list[str]:
    if not draft:
        return refined
    if len(refined) == len(draft):
        return refined
    if len(refined) > len(draft):
        return refined[: len(draft)]
    padded = list(refined)
    for i in range(len(refined), len(draft)):
        padded.append(apply_academic_search_suffix(draft[i]))
    return padded


def parse_refiner_json(raw: str, *, draft_queries: list[str]) -> SearchQueryRefinement:
    data = parse_json_object(raw)
    raw_queries = data.get("queries") or []
    if not isinstance(raw_queries, list):
        raise ValueError("queries must be a list")
    queries = _align_query_count(
        [
            clamp_search_query(str(q), max_len=SEARCH_QUERY_MAX, fallback="")
            for q in raw_queries
            if str(q).strip()
        ],
        draft_queries,
    )
    if len(queries) != len(draft_queries):
        queries = _align_query_count(queries, draft_queries)
    for i, q in enumerate(queries):
        if not q:
            queries[i] = apply_academic_search_suffix(draft_queries[i])
    exclusions = _normalize_exclusions(data.get("exclude_title_substrings") or [])
    questions = _normalize_questions(data.get("clarification_questions") or [])
    return SearchQueryRefinement(
        queries=queries,
        exclude_title_substrings=exclusions,
        clarification_questions=questions,
    )


async def refine_literature_search_queries(
    draft_queries: list[str],
    *,
    user_message: str = "",
    llm=None,
    use_llm: bool = True,
) -> SearchQueryRefinement:
    """Refine draft search queries with LLM; rule fallback on failure."""
    draft = _normalize_queries(draft_queries)
    if not draft:
        return SearchQueryRefinement(queries=[])

    if use_llm and llm is not None:
        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(draft))
        prompt = (
            f"【用户研究说明】\n{(user_message or '').strip()[:2000]}\n\n"
            f"【待精炼检索式草案】\n{numbered}\n\n"
            f"请对每条草案 1:1 消歧并规范化，输出 JSON；"
            f"queries 数组长度必须为 {len(draft)}，并填写 exclude_title_substrings。"
        )
        try:
            refiner_system = await get_search_refiner_system_prompt()
            resp = await llm.chat(
                [LLMMessage(role="user", content=prompt)],
                system=refiner_system,
                max_tokens=640,
                temperature=0.1,
            )
            return parse_refiner_json(resp.content or "", draft_queries=draft)
        except Exception:
            _log.exception("LLM search query refine failed; using rule fallback")

    return refine_search_queries_rule(draft, user_message=user_message)


async def assess_first_turn_clarification(
    user_message: str,
    search_query: str,
    *,
    llm=None,
    use_llm: bool = True,
) -> list[str]:
    """Ask LLM whether first-turn brief needs clarification before retrieval."""
    draft = clamp_search_query(search_query, fallback=user_message[:120])
    if not use_llm or llm is None or not draft:
        return []
    refinement = await refine_literature_search_queries(
        [draft],
        user_message=user_message,
        llm=llm,
        use_llm=True,
    )
    return list(refinement.clarification_questions)
