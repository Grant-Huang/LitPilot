"""LLM first-turn brief assessment — extract RQ/keywords; clarify only when needed."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.llm_json import parse_json_object
from app.agents.prompt_registry import DEFAULT_ASSESSOR_SYSTEM as ASSESSOR_SYSTEM
from app.agents.prompt_settings import get_assessor_system_prompt
from app.agents.literature_router import SEARCH_QUERY_MAX, clamp_search_query
from app.agents.search_query_refiner import apply_academic_search_suffix
from app.llm.base import LLMMessage

_log = logging.getLogger(__name__)

_VAGUE_BRIEF_RE = re.compile(
    r"^(?:请|帮我|帮忙)?(?:写|做|来)?(?:一个|一篇)?(?:文献)?综述(?:吧|。?)?$",
    re.I,
)

@dataclass
class ClarificationChoice:
    prompt: str
    options: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"prompt": self.prompt, "options": list(self.options)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClarificationChoice | None:
        prompt = str(data.get("prompt") or "").strip()
        opts = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
        if not prompt or len(opts) < 2:
            return None
        return cls(prompt=prompt[:300], options=opts[:5])


@dataclass
class FirstTurnAssessment:
    sufficient: bool = False
    confidence: str = "low"
    core_research_questions: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    search_query_hint: str = ""
    clarification: list[ClarificationChoice] = field(default_factory=list)

    def needs_user_gate(self) -> bool:
        if not self.clarification:
            return False
        if self.sufficient and self.confidence == "high":
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "confidence": self.confidence,
            "core_research_questions": list(self.core_research_questions),
            "keywords": list(self.keywords),
            "search_query_hint": self.search_query_hint,
            "clarification": [c.to_dict() for c in self.clarification],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FirstTurnAssessment | None:
        if not isinstance(data, dict):
            return None
        choices: list[ClarificationChoice] = []
        for raw in data.get("clarification") or []:
            if isinstance(raw, dict):
                ch = ClarificationChoice.from_dict(raw)
                if ch:
                    choices.append(ch)
        return cls(
            sufficient=bool(data.get("sufficient")),
            confidence=str(data.get("confidence") or "low").strip().lower(),
            core_research_questions=[
                str(q).strip()[:400]
                for q in (data.get("core_research_questions") or [])
                if str(q).strip()
            ][:4],
            keywords=[
                str(k).strip()[:80]
                for k in (data.get("keywords") or [])
                if str(k).strip()
            ][:10],
            search_query_hint=str(data.get("search_query_hint") or "").strip()[:500],
            clarification=choices,
        )


def _looks_like_topic_stub(msg: str) -> bool:
    tokens = [t for t in re.split(r"\s+", msg.strip()) if t]
    if len(tokens) >= 2 and len(msg.strip()) >= 10:
        return True
    if re.search(r"[A-Za-z]{4,}", msg):
        return True
    return False


def _normalize_confidence(raw: str) -> str:
    c = (raw or "").strip().lower()
    if c in ("high", "medium", "low"):
        return c
    return "low"


def _normalize_choices(raw: list) -> list[ClarificationChoice]:
    out: list[ClarificationChoice] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ch = ClarificationChoice.from_dict(item)
        if ch:
            out.append(ch)
    return out[:3]


def parse_assessor_json(raw: str) -> FirstTurnAssessment:
    data = parse_json_object(raw)
    questions = [
        str(q).strip()[:400]
        for q in (data.get("core_research_questions") or [])
        if str(q).strip()
    ]
    keywords = [
        str(k).strip()[:80]
        for k in (data.get("keywords") or [])
        if str(k).strip()
    ]
    hint = clamp_search_query(
        str(data.get("search_query_hint") or ""),
        max_len=SEARCH_QUERY_MAX,
        fallback="",
    )
    if hint and "survey" not in hint.lower() and "peer-reviewed" not in hint.lower():
        hint = apply_academic_search_suffix(hint)[:SEARCH_QUERY_MAX]

    return FirstTurnAssessment(
        sufficient=bool(data.get("sufficient")),
        confidence=_normalize_confidence(str(data.get("confidence") or "")),
        core_research_questions=questions[:4],
        keywords=keywords[:10],
        search_query_hint=hint,
        clarification=_normalize_choices(data.get("clarification") or []),
    )


def rule_fallback_assessment(user_message: str) -> FirstTurnAssessment | None:
    """Minimal gate when LLM unavailable and brief is clearly too vague."""
    msg = (user_message or "").strip()
    if not msg:
        return None
    if (len(msg) >= 20 or _looks_like_topic_stub(msg)) and not _VAGUE_BRIEF_RE.match(msg):
        return None
    return FirstTurnAssessment(
        sufficient=False,
        confidence="low",
        clarification=[
            ClarificationChoice(
                prompt="你这轮综述主要希望覆盖哪类来源？",
                options=[
                    "学术期刊 / 会议论文",
                    "行业白皮书 / 标准 / 技术报告",
                    "二者都需要",
                    "其他（请说明）",
                ],
            ),
        ],
    )


async def assess_first_turn_brief(
    user_message: str,
    *,
    search_query: str = "",
    llm=None,
    use_llm: bool = True,
) -> FirstTurnAssessment:
    msg = (user_message or "").strip()
    if not msg:
        return FirstTurnAssessment()

    if use_llm and llm is not None:
        router_hint = clamp_search_query(
            search_query,
            max_len=SEARCH_QUERY_MAX,
            fallback=msg[:120],
        )
        prompt = (
            f"【用户首轮说明】\n{msg[:2500]}\n\n"
            f"【路由/检索草案（可能含噪声，勿复述）】\n{router_hint or '（无）'}\n\n"
            "请输出 JSON。"
        )
        try:
            assessor_system = await get_assessor_system_prompt()
            resp = await llm.chat(
                [LLMMessage(role="user", content=prompt)],
                system=assessor_system,
                max_tokens=720,
                temperature=0.15,
            )
            return parse_assessor_json(resp.content or "")
        except Exception:
            _log.exception("LLM first-turn assess failed; using rule fallback")

    fb = rule_fallback_assessment(msg)
    return fb or FirstTurnAssessment(
        sufficient=True,
        confidence="medium",
        search_query_hint=clamp_search_query(msg, fallback=msg[:120]),
    )


def format_brief_assessment_message(assessment: FirstTurnAssessment) -> str:
    """Markdown block shown in chat when brief is sufficient (no clarification gate)."""
    rqs = [q.strip() for q in assessment.core_research_questions if q.strip()]
    kws = [k.strip() for k in assessment.keywords if k.strip()]
    if not rqs and not kws:
        return ""
    lines = ["**已理解你的研究需求**", ""]
    if rqs:
        lines.append("**核心研究问题**")
        for i, q in enumerate(rqs, 1):
            lines.append(f"{i}. {q}")
        lines.append("")
    if kws:
        lines.append(f"**检索关键词**：{' · '.join(kws)}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
