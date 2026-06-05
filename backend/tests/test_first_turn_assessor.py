import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.first_turn_assessor import (
    FirstTurnAssessment,
    assess_first_turn_brief,
    parse_assessor_json,
    rule_fallback_assessment,
)
from app.agents.literature_clarification import (
    assessment_to_gate,
    assess_first_turn_gate,
    format_gate_message,
    merge_first_turn_message,
    resolve_pending_gate,
)

MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。"""


def test_parse_assessor_json_sufficient() -> None:
    raw = json.dumps(
        {
            "sufficient": True,
            "confidence": "high",
            "core_research_questions": ["What is AI-native MOM?"],
            "keywords": ["AI-native MOM", "manufacturing operations"],
            "search_query_hint": "AI-native MOM manufacturing survey peer-reviewed",
            "clarification": [],
        }
    )
    a = parse_assessor_json(raw)
    assert a.sufficient is True
    assert a.confidence == "high"
    assert not a.needs_user_gate()


def test_assessment_to_gate_skips_when_sufficient() -> None:
    a = FirstTurnAssessment(sufficient=True, confidence="high")
    assert assessment_to_gate(a, original_message="x") is None


def test_assessment_to_gate_choice_format() -> None:
    from app.agents.first_turn_assessor import ClarificationChoice

    a = FirstTurnAssessment(
        sufficient=False,
        confidence="low",
        clarification=[
            ClarificationChoice(
                prompt="「MOM」在此处主要指？",
                options=["Manufacturing Operations Management", "其他（请说明）"],
            )
        ],
    )
    gate = assessment_to_gate(a, original_message="MOM 综述")
    assert gate is not None
    msg = format_gate_message(gate)
    assert "MOM" in msg
    assert "A." in msg


def test_rule_fallback_only_for_vague() -> None:
    assert rule_fallback_assessment("帮我写个综述") is not None
    assert rule_fallback_assessment(MOM_BRIEF) is None


@pytest.mark.asyncio
async def test_assess_first_turn_gate_skips_rich_brief() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                {
                    "sufficient": True,
                    "confidence": "high",
                    "core_research_questions": ["RQ1"],
                    "keywords": ["AI-native MOM"],
                    "search_query_hint": "AI-native MOM survey peer-reviewed",
                    "clarification": [],
                }
            )
        )
    )
    gate, assessment = await assess_first_turn_gate(
        MOM_BRIEF,
        search_query=MOM_BRIEF[:120],
        user_turns=1,
        intent="new_topic",
        gate_resolved={},
        llm=llm,
    )
    assert gate is None
    assert assessment is not None
    assert assessment.sufficient is True


@pytest.mark.asyncio
async def test_assess_first_turn_brief_llm_clarify() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                {
                    "sufficient": False,
                    "confidence": "low",
                    "core_research_questions": [],
                    "keywords": [],
                    "search_query_hint": "",
                    "clarification": [
                        {
                            "prompt": "「MOM」主要指？",
                            "options": ["制造运营管理", "其他（请说明）"],
                        }
                    ],
                }
            )
        )
    )
    out = await assess_first_turn_brief("MOM", llm=llm)
    assert out.needs_user_gate()
    gate = assessment_to_gate(out, original_message="MOM")
    assert gate is not None
    res = resolve_pending_gate(gate, "A")
    assert res.action == "provide_context"


def test_format_brief_assessment_message() -> None:
    from app.agents.first_turn_assessor import format_brief_assessment_message

    msg = format_brief_assessment_message(
        FirstTurnAssessment(
            core_research_questions=["What is AI-native MOM?", "How to build trust?"],
            keywords=["AI-native MOM", "knowledge graph"],
        )
    )
    assert "核心研究问题" in msg
    assert "What is AI-native MOM?" in msg
    assert "检索关键词" in msg
    assert "knowledge graph" in msg


def test_merge_first_turn_message() -> None:
    merged = merge_first_turn_message("写综述", "主题是 AI-native MOM 制造运营")
    assert "写综述" in merged
    assert "AI-native MOM" in merged
