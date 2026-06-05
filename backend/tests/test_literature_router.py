from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.literature_router import (
    LiteratureRouterResult,
    _sanitize_session_title,
    refine_router_session_title,
    route_literature,
    should_auto_rename_session,
    title_is_message_truncation,
)
from app.storage.file_store import is_default_session_title


def test_is_default_session_title() -> None:
    assert is_default_session_title("新综述")
    assert is_default_session_title("")
    assert not is_default_session_title("大模型幻觉综述")


def test_sanitize_rejects_generic() -> None:
    assert "transformer" in _sanitize_session_title("新综述", "transformer papers").lower()


def test_title_is_message_truncation() -> None:
    long_q = (
        "I want a literature review on AI-native MOM covering four aspects: "
        "definitions, trust, multi-agent systems, and migration paths."
    )
    assert title_is_message_truncation(long_q[:40] + "…", long_q)
    assert title_is_message_truncation(long_q[:40], long_q)
    assert not title_is_message_truncation("AI-native MOM review", long_q)


def test_should_auto_rename_truncated_title() -> None:
    long_q = (
        "I want a literature review on AI-native MOM covering four aspects: "
        "definitions, trust, multi-agent systems, and migration paths."
    )
    assert should_auto_rename_session(
        {"title": long_q[:40] + "…"},
        long_q,
        user_message_count=1,
    )


def test_should_auto_rename_first_turn_default() -> None:
    assert should_auto_rename_session(
        {"title": "新综述"},
        "LLM alignment survey",
        user_message_count=1,
    )
    assert not should_auto_rename_session(
        {"title": "我的课题"},
        "hello",
        user_message_count=1,
    )
    assert not should_auto_rename_session(
        {"title": "新综述"},
        "hello",
        user_message_count=2,
    )
    assert not should_auto_rename_session(
        {"title": "新综述", "title_auto_set": True},
        "hello again",
        user_message_count=2,
    )


@pytest.mark.asyncio
async def test_route_literature_parses_json() -> None:
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content='{"session_title":"大模型幻觉研究","search_query":"LLM hallucination survey"}',
        ),
    )
    with patch(
        "app.agents.literature_router.get_planner_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        result = await route_literature("What causes hallucination in LLMs?")
    assert isinstance(result, LiteratureRouterResult)
    assert result.session_title == "大模型幻觉研究"
    assert "hallucination" in result.search_query.lower()


@pytest.mark.asyncio
async def test_refine_router_session_title_calls_dedicated_router() -> None:
    long_q = (
        "I want a literature review on AI-native MOM covering four aspects: "
        "definitions, trust, multi-agent systems, and migration paths."
    )
    truncated = LiteratureRouterResult(
        session_title=long_q[:40] + "…",
        search_query="q",
    )
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=(
                '{"session_title":"AI原生制造运营综述",'
                '"search_query":"AI-native MOM manufacturing survey"}'
            ),
        ),
    )
    with patch(
        "app.agents.literature_router.get_planner_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        refined = await refine_router_session_title(truncated, long_q)
    assert refined.session_title == "AI原生制造运营综述"
    assert "MOM" in refined.search_query


@pytest.mark.asyncio
async def test_refine_router_skips_when_title_already_summary() -> None:
    good = LiteratureRouterResult(
        session_title="AI原生制造运营综述",
        search_query="AI-native MOM",
    )
    with patch(
        "app.agents.literature_router.route_literature",
        new_callable=AsyncMock,
    ) as mock_route:
        refined = await refine_router_session_title(good, "long user question")
    mock_route.assert_not_called()
    assert refined.session_title == "AI原生制造运营综述"


@pytest.mark.asyncio
async def test_route_literature_fallback_on_error() -> None:
    with patch(
        "app.agents.literature_router.get_planner_llm",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no llm"),
    ):
        result = await route_literature("short topic")
    assert result.session_title == "short topic"
    assert result.search_query == "short topic"
