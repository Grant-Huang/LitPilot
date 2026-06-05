"""Tests for dynamic narration_focus / writing_emphasis on router result."""
from __future__ import annotations

from app.agents.literature_router import build_router_result


def test_build_router_result_parses_focus_fields() -> None:
    data = {
        "session_title": "AI 制造综述",
        "search_query": "AI-native MES survey",
        "narration_focus": "侧重多智能体协同与知识图谱",
        "writing_emphasis": "按技术维度对比，突出工业落地",
        "needs_clarification": False,
        "clarification_questions": [],
    }
    result = build_router_result(data, "AI-native MES literature review")
    assert result.narration_focus == "侧重多智能体协同与知识图谱"
    assert result.writing_emphasis == "按技术维度对比，突出工业落地"


def test_build_router_result_truncates_focus_fields() -> None:
    data = {
        "session_title": "主题",
        "search_query": "query",
        "narration_focus": "a" * 400,
        "writing_emphasis": "b" * 400,
    }
    result = build_router_result(data, "topic")
    assert len(result.narration_focus) == 300
    assert len(result.writing_emphasis) == 300
