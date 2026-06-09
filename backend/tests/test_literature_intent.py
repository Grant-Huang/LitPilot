"""Tests for v2 literature intent routing."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.literature_intent import (
    CORPUS_GUIDANCE_FOOTER,
    LiteratureIntentResult,
    build_append_urls_notice,
    build_generation_prompt,
    build_query_prompt,
    build_session_turn_context,
    detect_intent_rules,
    merge_gen_constraints,
    normalize_intent,
    route_literature_intent,
)
from app.agents.session_corpus import SessionCorpus, filter_new_urls


def _make_corpus() -> SessionCorpus:
    c = SessionCorpus()
    c.sources_md.append("## [网页材料] Sample\n\ncontent")
    c.fetch_hits.append({"url": "https://example.com/a", "title": "A"})
    c.register_url("https://example.com/a")
    return c


def _turn_ctx(*, has_corpus: bool = True, user_turns: int = 2, failed: int = 0):
    corpus = _make_corpus() if has_corpus else None
    with patch(
        "app.agents.literature_intent.list_session_library_items",
        return_value=[],
    ):
        return build_session_turn_context(
            session_id="s1",
            session_meta={"initial_query": "LLM survey", "gen_constraints": []},
            user_turns=user_turns,
            corpus=corpus,
            last_failed=[{"url": "https://fail.example/x"}] if failed else [],
            has_review=True,
        )


def test_first_turn_is_new_topic_ignores_urls() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    result = detect_intent_rules(
        "transformer survey papers",
        turn_ctx=ctx,
        extra_urls=["https://example.com/paper"],
    )
    assert result is not None
    assert result.intent == "new_topic"
    assert result.new_urls == []


def test_append_urls_with_url() -> None:
    ctx = _turn_ctx()
    corpus = _make_corpus()
    result = detect_intent_rules(
        "再加这篇 https://arxiv.org/abs/2301.00001",
        turn_ctx=ctx,
        corpus=corpus,
    )
    assert result is not None
    assert result.intent == "append_urls"
    assert result.skip_web_search is True
    assert result.defer_generate is True
    assert result.new_urls


def test_subtopic_add_explicit() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "增加子主题：零信任架构",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "subtopic_change"
    assert result.subtopic_op == "add"


def test_subtopic_modify_explicit() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "修改子主题 2：改为供应链韧性",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "subtopic_change"
    assert result.subtopic_op == "modify"


def test_expand_search_hint_falls_to_llm() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "再搜一些 trust 相关文献",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    # No rule matches — falls through to LLM (returns None from rules)
    assert result is None


def test_review_refine_keywords() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "只重写第二章，改为表格对比",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "review_refine"
    assert result.skip_fetch is True


def test_query_corpus() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "Smith 2022 这篇的核心结论是什么？",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "query_corpus"


def test_query_prompt_includes_guidance() -> None:
    prompt = build_query_prompt(
        initial_query="topic",
        user_message="有多少篇？",
        context_block="materials",
    )
    assert CORPUS_GUIDANCE_FOOTER.strip() in prompt


def test_filter_new_urls_dedupes() -> None:
    corpus = SessionCorpus()
    corpus.register_url("https://arxiv.org/abs/2301.00001")
    urls = filter_new_urls(
        corpus,
        ["https://arxiv.org/abs/2301.00001", "https://example.com/new"],
    )
    assert len(urls) == 1
    assert urls[0] == "https://example.com/new"


def test_merge_gen_constraints() -> None:
    out = merge_gen_constraints(["a"], "b")
    assert out == ["a", "b"]
    out2 = merge_gen_constraints(["a"], "a")
    assert out2 == ["a"]


def test_normalize_legacy_intents() -> None:
    assert normalize_intent("supplement") == "append_urls"
    assert normalize_intent("refine_gen") == "review_refine"
    assert normalize_intent("regen_only") == "review_refine"
    assert normalize_intent("expand_search") == "short_answer"
    assert normalize_intent("unknown_intent") == "short_answer"


def test_build_append_urls_notice() -> None:
    text = build_append_urls_notice(
        updated_titles=["Paper A"],
        chapter_hints=["第二章"],
    )
    assert "Paper A" in text
    assert "第二章" in text


def test_build_generation_prompt_materials_only() -> None:
    prompt = build_generation_prompt(
        initial_query="topic",
        user_message="more",
        intent=LiteratureIntentResult(
            intent="review_refine",
            gen_directives="focus on ethics",
        ),
        gen_constraints=["use tables"],
        context_block="materials",
    )
    assert "materials" in prompt


@pytest.mark.asyncio
async def test_second_turn_calls_router_llm() -> None:
    """2nd+ turn with ambiguous message should call LLM router (intent_router_system_template)."""
    ctx = _turn_ctx(has_corpus=True, user_turns=2)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(
        return_value=type("Resp", (), {"content": '{"intent": "review_refine", "gen_directives": "focus on methodology"}'})()
    )

    with patch(
        "app.agents.literature_intent.get_router_llm",
        return_value=mock_llm,
    ):
        result = await route_literature_intent(
            "请着重讨论方法论方面的内容",
            turn_ctx=ctx,
            corpus=_make_corpus(),
        )

    mock_llm.chat.assert_called_once()
    assert result.intent == "review_refine"
    assert "methodology" in result.gen_directives


@pytest.mark.asyncio
async def test_second_turn_llm_fallback_on_failure() -> None:
    """2nd+ turn should not crash when LLM fails; fallback to short_answer."""
    ctx = _turn_ctx(has_corpus=True, user_turns=2)

    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

    with patch(
        "app.agents.literature_intent.get_router_llm",
        return_value=mock_llm,
    ):
        result = await route_literature_intent(
            "请着重讨论方法论方面的内容",
            turn_ctx=ctx,
            corpus=_make_corpus(),
        )

    mock_llm.chat.assert_called_once()
    # On failure, falls back to short_answer
    assert result.intent in ("short_answer", "review_refine")
