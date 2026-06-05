from app.agents.literature_clarification import (
    build_outline_confirm_gate,
    detect_search_zero_gate,
    merge_first_turn_message,
    resolve_pending_gate,
)
from app.schemas.literature_outline import LiteratureOutline, OutlineSection, ResearchSubTopic


def test_detect_search_zero_gate() -> None:
    gate = detect_search_zero_gate(
        hits=[],
        upload_urls=[],
        skip_web_search=False,
        query="AI-native MOM survey",
        answer="some summary",
        gate_resolved={},
    )
    assert gate is not None
    assert gate.kind == "search_zero"


def test_resolve_search_zero_relax() -> None:
    gate = detect_search_zero_gate(
        hits=[],
        upload_urls=[],
        skip_web_search=False,
        query="q",
        answer="",
        gate_resolved={},
    )
    assert gate is not None
    res = resolve_pending_gate(gate, "放宽检索")
    assert res.action == "relax_domain"


def test_merge_first_turn_message() -> None:
    merged = merge_first_turn_message("原始问题", "补充：聚焦 MES")
    assert "原始问题" in merged
    assert "MES" in merged


def test_build_outline_confirm_gate() -> None:
    outline = LiteratureOutline(
        topic="AI MOM",
        sections=[
            OutlineSection(
                id="s1",
                number="1",
                title="背景",
                desc="概述",
            )
        ],
        sub_topics=[
            ResearchSubTopic(
                id="st1",
                title="子题",
                description="",
                search_query="q",
            )
        ],
    )
    gate = build_outline_confirm_gate(outline)
    assert gate.kind == "outline_confirm"
    assert gate.questions
