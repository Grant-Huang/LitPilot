"""Tests for multi-turn literature intent routing."""
from __future__ import annotations

from app.agents.literature_intent import (
    LiteratureIntentResult,
    build_generation_prompt,
    build_session_turn_context,
    detect_intent_rules,
    execute_manage_library,
    merge_gen_constraints,
    parse_manage_command,
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
    return build_session_turn_context(
        session_id="s1",
        session_meta={"initial_query": "LLM survey", "gen_constraints": []},
        user_turns=user_turns,
        corpus=corpus,
        last_failed=[{"url": "https://fail.example/x"}] if failed else [],
        has_review=True,
    )


def test_first_turn_is_new_topic() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    result = detect_intent_rules("transformer survey papers", turn_ctx=ctx)
    assert result is not None
    assert result.intent == "new_topic"


def test_supplement_with_url() -> None:
    ctx = _turn_ctx()
    corpus = _make_corpus()
    result = detect_intent_rules(
        "再加这篇 https://arxiv.org/abs/2301.00001",
        turn_ctx=ctx,
        corpus=corpus,
    )
    assert result is not None
    assert result.intent == "supplement"
    assert result.skip_tavily is True
    assert result.new_urls


def test_refine_gen_keywords() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "重点写医疗影像方向，增加伦理一节",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "refine_gen"
    assert result.skip_fetch is True


def test_synthesis_matrix_reuses_existing_corpus() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "请基于已有文献生成一个 Synthesis Matrix",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "synthesis_matrix"
    assert result.skip_tavily is True
    assert result.skip_fetch is True
    assert result.use_existing_corpus is True


def test_synthesis_matrix_first_turn_searches() -> None:
    ctx = _turn_ctx(has_corpus=False, user_turns=1)
    result = detect_intent_rules(
        "AI-Native MOM 架构重构文献综述矩阵",
        turn_ctx=ctx,
    )
    assert result is not None
    assert result.intent == "synthesis_matrix"
    assert result.skip_tavily is False
    assert result.skip_fetch is False
    assert result.use_existing_corpus is False


def test_retry_failed() -> None:
    ctx = _turn_ctx(failed=1)
    result = detect_intent_rules(
        "重试刚才失败的链接",
        turn_ctx=ctx,
        corpus=_make_corpus(),
        last_failed=[{"url": "https://fail.example/x"}],
    )
    assert result is not None
    assert result.intent == "retry_failed"
    assert "fail.example" in result.new_urls[0]


def test_query_corpus() -> None:
    ctx = _turn_ctx()
    result = detect_intent_rules(
        "Smith 2022 这篇的核心结论是什么？",
        turn_ctx=ctx,
        corpus=_make_corpus(),
    )
    assert result is not None
    assert result.intent == "query_corpus"


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


def test_build_generation_prompt_materials_only() -> None:
    prompt = build_generation_prompt(
        initial_query="topic",
        user_message="more",
        intent=LiteratureIntentResult(
            intent="refine_gen",
            gen_directives="focus on ethics",
        ),
        gen_constraints=["use tables"],
        context_block="materials",
    )
    assert "materials" in prompt
    assert "用户研究问题" not in prompt
    assert "focus on ethics" not in prompt


def test_parse_manage_export() -> None:
    action, targets = parse_manage_command("导出参考文献", "s1")
    assert action == "export_refs"
    assert targets == []


def test_execute_manage_list_empty() -> None:
    text = execute_manage_library("list", [], "no-such-session")
    assert "尚无" in text or "文献库" in text
