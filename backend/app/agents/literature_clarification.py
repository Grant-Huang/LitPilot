"""Clarification gates — pause turn for user input at key decision points."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.first_turn_assessor import (
    ClarificationChoice,
    FirstTurnAssessment,
    assess_first_turn_brief,
)
from app.agents.literature_router import clamp_search_query
from app.agents.url_list import parse_urls_from_text

ClarificationKind = Literal["first_turn", "search_zero", "outline_confirm"]

_CONFIRM_RE = re.compile(
    r"^(?:确认|继续|开始写|开始撰写|ok|yes|好的|可以|没问题)\.?$",
    re.I,
)
_RELAX_SEARCH_RE = re.compile(r"放宽(?:检索|域名|限制)?|relax", re.I)
_ABORT_RE = re.compile(r"^(?:取消|停止|终止|算了)\.?$", re.I)
_OPTION_LETTERS = "ABCDEFGH"


@dataclass
class ClarificationGate:
    kind: ClarificationKind
    questions: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    choices: list[ClarificationChoice] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "questions": list(self.questions),
            "context": dict(self.context),
            "choices": [c.to_dict() for c in self.choices],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ClarificationGate | None:
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind") or "").strip()
        if kind not in ("first_turn", "search_zero", "outline_confirm"):
            return None
        questions = [str(q) for q in (data.get("questions") or []) if str(q).strip()]
        choices: list[ClarificationChoice] = []
        for raw in data.get("choices") or []:
            if isinstance(raw, dict):
                ch = ClarificationChoice.from_dict(raw)
                if ch:
                    choices.append(ch)
        if not questions and not choices:
            return None
        return cls(
            kind=kind,  # type: ignore[arg-type]
            questions=questions,
            context=dict(data.get("context") or {}),
            choices=choices,
        )

    def to_sse_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "questions": self.questions,
            "choices": [c.to_dict() for c in self.choices],
            **{k: v for k, v in self.context.items() if k != "questions"},
        }


@dataclass
class GateResolution:
    kind: ClarificationKind
    action: str
    merge_text: str = ""
    search_query: str = ""
    new_urls: list[str] = field(default_factory=list)


@dataclass
class ClarificationState:
    """Per-turn flags after resolving a pending gate or from session history."""

    resolved: dict[str, bool] = field(default_factory=dict)
    search_relax_domain: bool = False
    search_retry_query: str = ""
    first_turn_supplement: str = ""
    outline_edit_directives: str = ""
    extra_urls: list[str] = field(default_factory=list)
    resume_generate_only: bool = False
    aborted: bool = False

    @classmethod
    def from_session(cls, meta: dict[str, Any] | None) -> ClarificationState:
        resolved = dict((meta or {}).get("gate_resolved") or {})
        return cls(resolved={k: bool(v) for k, v in resolved.items()})

    def apply(self, resolution: GateResolution) -> None:
        self.resolved[resolution.kind] = True
        if resolution.action == "abort":
            self.aborted = True
            return
        if resolution.kind == "first_turn":
            self.first_turn_supplement = resolution.merge_text.strip()
        elif resolution.kind == "search_zero":
            if resolution.action == "relax_domain":
                self.search_relax_domain = True
            elif resolution.action == "retry_query":
                self.search_retry_query = resolution.search_query.strip()
            if resolution.new_urls:
                self.extra_urls = list(resolution.new_urls)
        elif resolution.kind == "outline_confirm":
            if resolution.action == "edit":
                self.outline_edit_directives = resolution.merge_text.strip()
            self.resume_generate_only = True

    def mark_resolved(self, kind: ClarificationKind) -> dict[str, bool]:
        self.resolved[kind] = True
        return dict(self.resolved)


def _format_choice_block(choice: ClarificationChoice) -> list[str]:
    lines = [choice.prompt]
    for j, opt in enumerate(choice.options):
        letter = _OPTION_LETTERS[j] if j < len(_OPTION_LETTERS) else str(j + 1)
        lines.append(f"   {letter}. {opt}")
    return lines


def format_gate_message(gate: ClarificationGate) -> str:
    lines = ["**需要你补充或确认：**", ""]
    if gate.choices:
        for i, choice in enumerate(gate.choices, start=1):
            block = _format_choice_block(choice)
            if len(gate.choices) > 1:
                block[0] = f"{i}. {block[0]}"
            lines.extend(block)
            lines.append("")
    for i, q in enumerate(gate.questions, start=1):
        if len(gate.questions) == 1 or q.endswith("？") or q.endswith("?"):
            lines.append(q)
        else:
            lines.append(f"{i}. {q}")
    if gate.choices:
        lines.append(
            "_可直接回复选项字母（如 A、B）或用自己的话说明；回复后将自动继续，回复「取消」可终止本轮。_"
        )
    else:
        lines.append("")
        lines.append("_回复后将自动继续；回复「取消」可终止本轮。_")
    return "\n".join(lines).strip()


def assessment_to_gate(
    assessment: FirstTurnAssessment,
    *,
    original_message: str,
) -> ClarificationGate | None:
    if not assessment.needs_user_gate():
        return None
    questions: list[str] = []
    if not assessment.clarification:
        questions = [
            "请补充 1–2 句核心研究问题，或给出 2–4 个英文检索关键词。",
        ]
    return ClarificationGate(
        kind="first_turn",
        questions=questions,
        choices=list(assessment.clarification),
        context={
            "original_message": original_message[:500],
            "partial_assessment": assessment.to_dict(),
        },
    )


async def assess_first_turn_gate(
    user_message: str,
    *,
    search_query: str,
    user_turns: int,
    intent: str,
    gate_resolved: dict[str, bool],
    llm,
) -> tuple[ClarificationGate | None, FirstTurnAssessment | None]:
    """LLM assess brief; return gate only when clarification is truly needed."""
    if gate_resolved.get("first_turn"):
        return None, None
    if user_turns != 1 or intent != "new_topic":
        return None, None
    msg = (user_message or "").strip()
    if not msg:
        return None, None

    assessment = await assess_first_turn_brief(
        msg,
        search_query=search_query,
        llm=llm,
        use_llm=llm is not None,
    )
    gate = assessment_to_gate(assessment, original_message=msg)
    if gate:
        return gate, assessment
    return None, assessment


def detect_search_zero_gate(
    *,
    hits: list[Any],
    upload_urls: list[str],
    skip_web_search: bool,
    query: str,
    answer: str,
    gate_resolved: dict[str, bool],
) -> ClarificationGate | None:
    if gate_resolved.get("search_zero"):
        return None
    if skip_web_search or upload_urls:
        return None
    if hits:
        return None
    return ClarificationGate(
        kind="search_zero",
        questions=[
            "本轮检索未命中可抓取的文献链接。你希望如何继续？",
            "回复「放宽检索」：临时放宽学术域名限制再搜一次",
            "或直接给出更具体的检索关键词 / 英文检索式",
            "也可粘贴论文、预印本或报告 URL",
        ],
        context={
            "query": (query or "")[:200],
            "has_search_answer": bool((answer or "").strip()),
        },
    )


def build_outline_confirm_gate(outline: Any) -> ClarificationGate:
    sections = getattr(outline, "sections", []) or []
    titles = [str(getattr(s, "title", "") or "") for s in sections if getattr(s, "title", None)]
    topic = str(getattr(outline, "topic", "") or "")
    return ClarificationGate(
        kind="outline_confirm",
        questions=[
            f"已为「{topic[:48] or '本主题'}」生成 {len(titles)} 个章节（见右侧「大纲」Tab）。",
            "回复「确认」或「继续」开始撰写综述；",
            "也可直接说明需要增删或调整的章节。",
        ],
        context={"section_titles": titles[:12], "section_count": len(titles)},
    )


def resolve_pending_gate(
    gate: ClarificationGate,
    user_message: str,
) -> GateResolution:
    msg = (user_message or "").strip()
    if _ABORT_RE.search(msg):
        return GateResolution(kind=gate.kind, action="abort")

    if gate.kind == "first_turn":
        if len(msg) < 1:
            return GateResolution(kind=gate.kind, action="abort")
        if len(msg) == 1 and msg.upper() in _OPTION_LETTERS and gate.choices:
            return GateResolution(kind=gate.kind, action="provide_context", merge_text=msg)
        if len(msg) < 2:
            return GateResolution(kind=gate.kind, action="abort")
        return GateResolution(kind=gate.kind, action="provide_context", merge_text=msg)

    if gate.kind == "search_zero":
        urls = parse_urls_from_text(msg)
        if urls:
            return GateResolution(
                kind=gate.kind,
                action="retry_query",
                new_urls=urls,
                merge_text=msg,
            )
        if _RELAX_SEARCH_RE.search(msg):
            return GateResolution(kind=gate.kind, action="relax_domain")
        if len(msg) >= 4:
            return GateResolution(
                kind=gate.kind,
                action="retry_query",
                search_query=clamp_search_query(msg),
                merge_text=msg,
            )
        return GateResolution(kind=gate.kind, action="abort")

    if gate.kind == "outline_confirm":
        if _CONFIRM_RE.match(msg):
            return GateResolution(kind=gate.kind, action="confirm")
        return GateResolution(kind=gate.kind, action="edit", merge_text=msg)

    return GateResolution(kind=gate.kind, action="abort")


def merge_first_turn_message(original: str, supplement: str) -> str:
    base = (original or "").strip()
    extra = (supplement or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    return f"{base}\n\n【用户补充】\n{extra}"
