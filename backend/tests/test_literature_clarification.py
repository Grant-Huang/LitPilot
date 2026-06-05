from app.agents.literature_clarification import (
    build_outline_confirm_gate,
    detect_first_turn_ambiguity,
    detect_search_zero_gate,
    merge_first_turn_message,
    resolve_pending_gate,
    router_understanding_sufficient,
)
from app.schemas.literature_outline import LiteratureOutline, OutlineSection, ResearchSubTopic


def test_detect_first_turn_ambiguity_short_brief() -> None:
    gate = detect_first_turn_ambiguity(
        "帮我写个综述",
        search_query="帮我写个综述",
        user_turns=1,
        intent="new_topic",
        gate_resolved={},
    )
    assert gate is not None
    assert gate.kind == "first_turn"


def test_detect_first_turn_skips_when_resolved() -> None:
    gate = detect_first_turn_ambiguity(
        "帮我写个综述",
        search_query="x",
        user_turns=1,
        intent="new_topic",
        gate_resolved={"first_turn": True},
    )
    assert gate is None


def test_detect_first_turn_skips_when_router_sufficient() -> None:
    gate = detect_first_turn_ambiguity(
        "帮我写个综述",
        search_query="AI-native manufacturing operations management survey",
        user_turns=1,
        intent="new_topic",
        gate_resolved={},
    )
    assert gate is None


def test_router_understanding_sufficient_compact_query() -> None:
    assert router_understanding_sufficient(
        "写综述",
        "knowledge graph manufacturing AI agents",
    )


def test_router_understanding_insufficient_polluted() -> None:
    assert not router_understanding_sufficient(
        "我要写文献综述，包括4个方面",
        "我要写文献综述，包括4个方面",
    )


def test_detect_search_zero_gate() -> None:
    gate = detect_search_zero_gate(
        hits=[],
        upload_urls=[],
        skip_tavily=False,
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
        skip_tavily=False,
        query="q",
        answer="",
        gate_resolved={},
    )
    assert gate is not None
    res = resolve_pending_gate(gate, "放宽检索")
    assert res.action == "relax_domain"


def test_resolve_outline_confirm() -> None:
    outline = LiteratureOutline(
        topic="AI MOM",
        sections=[OutlineSection(id="s1", number="1", title="导言", desc="")],
        sub_topics=[ResearchSubTopic(id="t1", title="子主题", description="", search_query="q")],
    )
    gate = build_outline_confirm_gate(outline)
    assert gate.kind == "outline_confirm"
    res = resolve_pending_gate(gate, "确认")
    assert res.action == "confirm"


def test_merge_first_turn_message() -> None:
    merged = merge_first_turn_message("写综述", "主题是 AI-native MOM 制造运营")
    assert "写综述" in merged
    assert "AI-native MOM" in merged
