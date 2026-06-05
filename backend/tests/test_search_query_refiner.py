import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.search_query_refiner import (
    SearchQueryRefinement,
    apply_academic_search_suffix,
    parse_refiner_json,
    refine_literature_search_queries,
    refine_search_queries_rule,
)

MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。"""


def test_apply_academic_search_suffix() -> None:
    q = apply_academic_search_suffix("graph neural networks")
    assert "academic survey" in q.lower()


def test_refine_search_queries_rule_preserves_count() -> None:
    draft = ["topic A", "topic B"]
    out = refine_search_queries_rule(draft, user_message=MOM_BRIEF)
    assert len(out.queries) == 2
    assert all("survey" in q.lower() or "peer-reviewed" in q.lower() for q in out.queries)


def test_parse_refiner_json_aligns_length() -> None:
    raw = json.dumps(
        {
            "queries": [
                "AI-native manufacturing operations management reference model survey",
            ],
            "exclude_title_substrings": ["mental health operational model"],
            "clarification_questions": [],
        }
    )
    out = parse_refiner_json(
        raw,
        draft_queries=["q1", "q2"],
    )
    assert len(out.queries) == 2
    assert "mental health operational model" in out.exclude_title_substrings[0]


@pytest.mark.asyncio
async def test_refine_literature_search_queries_uses_llm() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(
            content=json.dumps(
                {
                    "queries": [
                        "AI-native MOM manufacturing operations management ISA-95 survey peer-reviewed",
                        "heterogeneous machine trust manufacturing knowledge graph survey peer-reviewed",
                    ],
                    "exclude_title_substrings": ["mental health operational model"],
                    "clarification_questions": [],
                }
            )
        )
    )
    draft = ["AI原生MOM定义", "异构机器信任 知识图谱"]
    out = await refine_literature_search_queries(
        draft,
        user_message=MOM_BRIEF,
        llm=llm,
        use_llm=True,
    )
    assert isinstance(out, SearchQueryRefinement)
    assert len(out.queries) == 2
    assert "manufacturing" in out.queries[0].lower()
    assert out.exclude_title_substrings


@pytest.mark.asyncio
async def test_refine_literature_search_queries_fallback_on_llm_error() -> None:
    llm = MagicMock()
    llm.chat = AsyncMock(side_effect=RuntimeError("down"))
    out = await refine_literature_search_queries(
        ["federated learning privacy"],
        user_message="privacy in federated learning",
        llm=llm,
        use_llm=True,
    )
    assert len(out.queries) == 1
    assert "manufacturing" not in out.queries[0].lower()
