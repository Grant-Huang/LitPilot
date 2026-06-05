"""Clarification gates — pause turn for user input at key decision points."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.literature_query_rules import is_mom_ambiguous
from app.agents.literature_router import LiteratureRouterResult, clamp_search_query
from app.agents.research_decompose import decompose_research_brief, is_polluted_search_query
from app.agents.url_list import parse_urls_from_text

ClarificationKind = Literal["first_turn", "search_zero", "outline_confirm"]

_VAGUE_BRIEF_RE = re.compile(
    r"^(?:请|帮我|帮忙)?(?:写|做|来)?(?:一个|一篇)?(?:文献)?综述(?:吧|。?)?$",
    re.I,
)
_CONFIRM_RE = re.compile(
    r"^(?:确认|继续|开始写|开始撰写|ok|yes|好的|可以|没问题)\.?$",
    re.I,
)
_RELAX_SEARCH_RE = re.compile(r"放宽(?:检索|域名|限制)?|relax", re.I)
_ABORT_RE = re.compile(r"^(?:取消|停止|终止|算了)\.?$", re.I)


@dataclass
class ClarificationGate:
    kind: ClarificationKind
    questions: list[str]
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "questions": list(self.questions),
            "context": dict(self.context),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ClarificationGate | None:
        if not isinstance(data, dict):
            return None
        kind = str(data.get("kind") or "").strip()
        if kind not in ("first_turn", "search_zero", "outline_confirm"):
            return None
        questions = [str(q) for q in (data.get("questions") or []) if str(q).strip()]
        if not questions:
            return None
        return cls(
            kind=kind,  # type: ignore[arg-type]
            questions=questions,
            context=dict(data.get("context") or {}),
        )

    def to_sse_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "questions": self.questions,
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


def format_gate_message(gate: ClarificationGate) -> str:
    lines = ["**需要你补充或确认：**", ""]
    for i, q in enumerate(gate.questions, start=1):
        if len(gate.questions) == 1 or q.endswith("？") or q.endswith("?"):
            lines.append(q)
        else:
            lines.append(f"{i}. {q}")
    lines.append("")
    lines.append("_回复后将自动继续；回复「取消」可终止本轮。_")
    return "\n".join(lines)


def _looks_like_topic_stub(msg: str) -> bool:
    tokens = [t for t in re.split(r"\s+", msg.strip()) if t]
    if len(tokens) >= 2 and len(msg.strip()) >= 10:
        return True
    if re.search(r"[A-Za-z]{4,}", msg):
        return True
    return False


def router_understanding_sufficient(
    user_message: str,
    search_query: str,
) -> bool:
    """编排/router 已提炼出可检索的研究焦点时，无需首轮澄清。"""
    msg = (user_message or "").strip()
    q = (search_query or "").strip()
    if decompose_research_brief(msg, base_query=q):
        return True
    if q and not is_polluted_search_query(q) and len(q) >= 10:
        return True
    return False


def _orchestrator_understanding_sufficient(
    user_message: str,
    orchestrator: LiteratureRouterResult,
) -> bool:
    msg = (user_message or "").strip()
    q = (orchestrator.search_query or "").strip()
    if orchestrator.needs_clarification:
        return False
    if router_understanding_sufficient(msg, q):
        return True
    return bool(q and not is_polluted_search_query(q) and len(q) >= 10)


def detect_first_turn_ambiguity(
    user_message: str,
    *,
    search_query: str,
    user_turns: int,
    intent: str,
    gate_resolved: dict[str, bool],
    orchestrator: LiteratureRouterResult | None = None,
) -> ClarificationGate | None:
    if gate_resolved.get("first_turn"):
        return None
    if user_turns != 1 or intent != "new_topic":
        return None
    msg = (user_message or "").strip()
    if not msg:
        return None

    if orchestrator is not None:
        if _orchestrator_understanding_sufficient(msg, orchestrator):
            return None
        if orchestrator.needs_clarification and orchestrator.clarification_questions:
            return ClarificationGate(
                kind="first_turn",
                questions=list(orchestrator.clarification_questions),
                context={"original_message": msg[:500], "source": "orchestrator"},
            )

    eff_query = (
        (orchestrator.search_query if orchestrator else "") or search_query
    ).strip()
    if router_understanding_sufficient(msg, eff_query):
        return None

    questions: list[str] = []
    if (len(msg) < 20 and not _looks_like_topic_stub(msg)) or _VAGUE_BRIEF_RE.match(msg):
        questions = [
            "你的研究主题具体是什么？（领域、对象、时间范围）",
            "综述侧重学术文献还是行业白皮书/标准？",
            "期望引用格式可在设置中选择 APA / ACM。",
        ]
    elif is_mom_ambiguous(msg):
        questions = [
            "这里的 MOM 是指制造运营管理（Manufacturing Operations Management），"
            "还是机器学习中的 Mixture-of-Memories？",
            "请补充具体应用场景（如 MES/MOM 迁移、 shop-floor 等）。",
        ]
    else:
        questions = [
            "请用 1–2 句话概括核心研究问题（避免只写「写一篇综述」）。",
            "可补充 2–4 个希望覆盖的子方向或英文关键词，便于学术检索。",
        ]

    return ClarificationGate(
        kind="first_turn",
        questions=questions,
        context={"original_message": msg[:500]},
    )


def detect_search_zero_gate(
    *,
    hits: list[Any],
    upload_urls: list[str],
    skip_tavily: bool,
    query: str,
    answer: str,
    gate_resolved: dict[str, bool],
) -> ClarificationGate | None:
    if gate_resolved.get("search_zero"):
        return None
    if skip_tavily or upload_urls:
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
            "has_tavily_answer": bool((answer or "").strip()),
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
        if len(msg) < 4:
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
