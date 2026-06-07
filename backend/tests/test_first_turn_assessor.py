import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.first_turn_assessor import (
    FirstTurnAssessment,
    assess_first_turn_brief,
    brief_assessment_from_router,
    parse_assessor_json,
    rule_fallback_assessment,
)
from app.agents.literature_router import LiteratureRouterResult
from app.agents.search_aspects import SearchAspect

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


def test_rule_fallback_only_for_vague() -> None:
    assert rule_fallback_assessment("帮我写个综述") is not None
    assert rule_fallback_assessment(MOM_BRIEF) is None


def test_brief_assessment_from_router() -> None:
    router = LiteratureRouterResult(
        session_title="AI MOM",
        search_query="AI-native MOM survey",
        search_aspects=[
            SearchAspect(
                aspect_id=1,
                aspect_label="定义与架构",
                core_concepts=["MOM", "AI-native"],
                arxiv_query="AI-native MOM architecture survey",
            ),
            SearchAspect(
                aspect_id=2,
                aspect_label="可信与治理",
                core_concepts=["trust"],
                semantic_scholar_query="AI MOM trust governance",
            ),
        ],
    )
    assessment = brief_assessment_from_router(router)
    assert assessment.sufficient is True
    assert assessment.confidence == "high"
    assert len(assessment.core_research_questions) == 2
    assert "MOM" in assessment.keywords
    assert assessment.clarification == []


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
    assert out.clarification


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


