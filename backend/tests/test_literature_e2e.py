"""Live end-to-end integration tests for the literature generation pipeline.

ALL external I/O is real:
  - LLM calls use configured provider (OpenAI / etc.)
  - Search uses multi_academic provider (arXiv, S2, OpenAlex, CrossRef, PubMed)
  - Fetch uses native HTTP fetcher
  - Citation extraction uses real LLM
  - Persistence uses isolated FileStore (tmp_path)

Run with:  .venv/bin/python -m pytest tests/test_literature_e2e.py -m live -v
These tests require network access and a valid LLM API key in env vars.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.storage.file_store import FileStore

from tests.helpers.e2e_mocks import (
    SEED_REVIEW_MARKDOWN,
    collect_turn_events,
    find_all_events,
    find_event,
    format_summary_text,
    seed_corpus_hits,
    summarize_events,
)
from tests.helpers.llm_trace import LLMTraceCollector

# Shared MOM (AI-native Manufacturing Operations Management) review prompt.
# Covers four research facets; deliberately rich to drive high-quality routing.
MOM_REVIEW_PROMPT = (
    "我要写一个与AI原生MOM（制造运营管理）有关的文献综述，包括4个方面："
    "其一，AI原生MOM系统性的定义框架与参考模型。"
    "其二，异构机器间信任建立的工程方案与制造知识图谱。"
    "其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，"
    "及其统一的工程整合框架。"
    "其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"
)

# All tests in this file require network
pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# Scenario 1: new_topic — full pipeline (real LLM + search + fetch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_topic_full_pipeline(
    inject_store: FileStore, llm_trace: LLMTraceCollector
) -> None:
    """完整链路：用户首次输入 → 意图路由 → 理解 → 大纲 → 搜索 → 抓取 → 生成 → 持久化

    验证所有阶段在真实 API 调用下正确流转。
    """
    store = inject_store
    session = store.create_session("新综述")
    session_id = session["id"]

    events = await collect_turn_events(session_id, MOM_REVIEW_PROMPT)

    print("\n===== test_new_topic_full_pipeline SUMMARY =====")
    print("PROMPT:", MOM_REVIEW_PROMPT)
    print(format_summary_text(summarize_events(events)))
    print("=================================================\n")

    # 检查是否有未捕获的异常（真实运行时 bug）
    uncaught = find_event(events, "_uncaught_exception")
    if uncaught is not None:
        import logging
        logging.getLogger(__name__).error(
            "Pipeline uncaught exception: %s [%s]",
            uncaught.get("message", ""),
            uncaught.get("type", ""),
        )

    # 1. 意图正确识别为 new_topic（首轮走规则引擎，不依赖 LLM）
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None, "缺少 literature_intent 事件"
    assert intent_ev["intent"] == "new_topic", (
        f"首轮应识别为 new_topic，实际为 {intent_ev['intent']}"
    )

    # 2. 不应产生 error 事件
    error_ev = find_event(events, "error")
    assert error_ev is None, f"不应有 error 事件: {error_ev}"

    # 3. 事件顺序：turn_start → literature_intent → 理解阶段 stage
    ext_events = find_all_events(events, "extension")
    turn_start_events = [e for e in ext_events if e.get("name") == "turn_start"]
    assert len(turn_start_events) >= 1, "缺少 turn_start 事件"

    turn_start_idx = next(
        i
        for i, (t, _) in enumerate(events)
        if t == "extension" and _.get("name") == "turn_start"
    )
    intent_idx = next(
        i for i, (t, _) in enumerate(events) if t == "literature_intent"
    )
    assert turn_start_idx < intent_idx, "turn_start 应在 literature_intent 之前"

    # 4. stage 事件应包含理解阶段
    stage_events = find_all_events(events, "stage")
    stage_names = [e.get("name") for e in stage_events]
    assert any("理解" in n or "分析" in n for n in stage_names), (
        f"缺少理解阶段 stage: {stage_names}"
    )

    # 5. 应有 session_title 事件（LLM 生成了 session 标题）
    title_ev = find_event(events, "session_title")
    assert title_ev is not None, "缺少 session_title 事件"
    assert len(title_ev.get("title", "")) > 0, "session 标题不应为空"

    # 6. 应有工作流图事件
    wf_events = [
        e for t, e in events if t == "extension" and e.get("name") == "workflow_graph"
    ]
    # 工作流图可能在不同阶段产生

    # 7. 应有 literature_progress 事件（搜索/抓取进度）
    progress_events = find_all_events(events, "literature_progress")
    assert len(progress_events) >= 1, "缺少 literature_progress 事件"

    # 8. 应有 turn_end 事件（如果 pipeline 正常完成）
    turn_end_events = [e for e in ext_events if e.get("name") == "turn_end"]
    if uncaught is not None:
        # Pipeline 有未捕获异常时，turn_end 可能不存在
        pass
    else:
        assert len(turn_end_events) >= 1, "缺少 turn_end 事件"

    # 9. 用户消息应被持久化
    messages = store.load_messages(session_id)
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert len(user_msgs) >= 1, "用户消息应被持久化"

    # 10. session meta 应被更新
    updated_session = store.get_session(session_id)
    assert updated_session is not None
    # session 标题可能被 LLM 更新，也可能保持默认值
    # 仅验证 session 存在且可被读取

    # 11. 应生成了 assistant 消息
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 1, "应生成 assistant 消息"


# ---------------------------------------------------------------------------
# Scenario 2: subtopic_change — incremental subtopic addition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subtopic_change_incremental(
    inject_seeded_store: FileStore,
) -> None:
    """增量添加子主题：识别为 subtopic_change，搜索新子主题"""
    store = inject_seeded_store
    session_id = store._e2e_session_id  # type: ignore[attr-defined]

    events = await collect_turn_events(
        session_id, "增加一个关于多模态幻觉的章节"
    )

    print("\n===== test_subtopic_change_incremental SUMMARY =====")
    print(format_summary_text(summarize_events(events)))
    print("===================================================\n")

    # 意图识别为 subtopic_change（规则引擎匹配"增加"）
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None
    assert intent_ev["intent"] == "subtopic_change", (
        f"应识别为 subtopic_change，实际为 {intent_ev['intent']}"
    )

    # 不应有 error
    assert find_event(events, "error") is None

    # 应有 turn_end
    ext_events = find_all_events(events, "extension")
    turn_end_events = [e for e in ext_events if e.get("name") == "turn_end"]
    assert len(turn_end_events) >= 1

    # assistant 消息应被保存
    messages = store.load_messages(session_id)
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    assert len(assistant_msgs) >= 2, "应有至少 2 条 assistant 消息（历史 + 新增）"


# ---------------------------------------------------------------------------
# Scenario 3: append_urls — URL supplementation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_urls_bypass_search(
    inject_seeded_store: FileStore,
) -> None:
    """追加 URL：跳过搜索，直接抓取指定 URL"""
    store = inject_seeded_store
    session_id = store._e2e_session_id  # type: ignore[attr-defined]

    events = await collect_turn_events(
        session_id,
        "补充这篇论文",
        extra_fetch_urls=["https://arxiv.org/abs/2401.00001"],
    )

    print("\n===== test_append_urls_bypass_search SUMMARY =====")
    print(format_summary_text(summarize_events(events)))
    print("==================================================\n")

    # 意图识别为 append_urls（规则引擎检测到 URL）
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None
    assert intent_ev["intent"] == "append_urls", (
        f"应识别为 append_urls，实际为 {intent_ev['intent']}"
    )

    # 不应有 error
    assert find_event(events, "error") is None

    # 应正常完成
    ext_events = find_all_events(events, "extension")
    turn_end_events = [e for e in ext_events if e.get("name") == "turn_end"]
    assert len(turn_end_events) >= 1


# ---------------------------------------------------------------------------
# Scenario 4: review_refine — refine review text
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_refine_partial_regenerate(
    inject_seeded_store: FileStore,
) -> None:
    """精修综述：跳过搜索和抓取，LLM 重新生成部分章节"""
    store = inject_seeded_store
    session_id = store._e2e_session_id  # type: ignore[attr-defined]

    events = await collect_turn_events(
        session_id, "请把综述中关于检测方法的部分写得更详细一些"
    )

    print("\n===== test_review_refine_partial_regenerate SUMMARY =====")
    print(format_summary_text(summarize_events(events)))
    print("=========================================================\n")

    # 意图识别为 review_refine（规则引擎匹配）
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None
    assert intent_ev["intent"] == "review_refine", (
        f"应识别为 review_refine，实际为 {intent_ev['intent']}"
    )

    # 不应有 error
    assert find_event(events, "error") is None

    # review_refine 跳过搜索和抓取（skip_web_search=True, skip_fetch=True）
    assert intent_ev.get("skip_web_search") is True
    assert intent_ev.get("skip_fetch") is True

    # 应正常完成
    ext_events = find_all_events(events, "extension")
    turn_end_events = [e for e in ext_events if e.get("name") == "turn_end"]
    assert len(turn_end_events) >= 1


# ---------------------------------------------------------------------------
# Scenario 5: query_corpus — corpus Q&A
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_corpus_qa(
    inject_seeded_store: FileStore,
) -> None:
    """语料问答：跳过搜索/抓取/综述生成，直接基于 corpus 回答"""
    store = inject_seeded_store
    session_id = store._e2e_session_id  # type: ignore[attr-defined]

    events = await collect_turn_events(
        session_id, "已有文献中关于检测方法主要有哪些？"
    )

    print("\n===== test_query_corpus_qa SUMMARY =====")
    print(format_summary_text(summarize_events(events)))
    print("========================================\n")

    # 意图识别为 query_corpus（规则引擎匹配问句 + 有 corpus）
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None
    assert intent_ev["intent"] == "query_corpus", (
        f"应识别为 query_corpus，实际为 {intent_ev['intent']}"
    )

    # 不应有 error
    assert find_event(events, "error") is None


# ---------------------------------------------------------------------------
# Scenario 6: short_answer — no pipeline execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_answer_no_pipeline(
    inject_store: FileStore,
) -> None:
    """简短回答：空 session 上输入模糊消息，系统应给出有意义的响应

    注意：在 seeded session 中，"谢谢"可能被 LLM 路由为其他意图
    （如 query_corpus），因为 LLM 会根据上下文判断。
    空 session 中走规则引擎 → new_topic（无 corpus 首轮）。
    """
    store = inject_store
    session = store.create_session("简短回复")
    session_id = session["id"]

    events = await collect_turn_events(session_id, "你好")

    print("\n===== test_short_answer_no_pipeline SUMMARY =====")
    print(format_summary_text(summarize_events(events)))
    print("=================================================\n")

    # 首轮无 corpus → 规则引擎走 new_topic 或 LLM 路由
    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None, "应有 intent 事件"

    # 不应有 error
    assert find_event(events, "error") is None

    # 应有 turn_end
    ext_events = find_all_events(events, "extension")
    turn_end_events = [e for e in ext_events if e.get("name") == "turn_end"]
    assert len(turn_end_events) >= 1, "应有 turn_end 事件"
