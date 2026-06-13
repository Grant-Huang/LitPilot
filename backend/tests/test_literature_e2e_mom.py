"""Live E2E tests focused on the AI-native MOM (Manufacturing Operations
Management) literature review scenarios:

  1. First-turn full pipeline with the rich MOM prompt.
  2. Second-turn corpus Q&A grounded on the first turn's corpus.
  3. Submitting a batch of reference URLs (first 15 of docs/ref/ref-list.txt)
     as an append_urls turn.

Run with:  .venv/bin/python -m pytest tests/test_literature_e2e_mom.py -m live -v -s
"""
from __future__ import annotations

import pytest

from app.storage.file_store import FileStore

from tests.helpers.e2e_mocks import (
    collect_turn_events,
    find_all_events,
    find_event,
    format_summary_text,
    summarize_events,
)
from tests.test_literature_e2e import MOM_REVIEW_PROMPT

pytestmark = pytest.mark.live

# First 15 URLs extracted from docs/ref/ref-list.txt (the user-supplied
# reference list for the MOM review). Used by the append_urls scenario.
REF_LIST_URLS_TOP15: list[str] = [
    "https://www.scitepress.org/Link.aspx?doi=10.5220/0006776701750182",
    "https://www.semanticscholar.org/paper/An-AI-native-application-assemble-platform-for-of-Jin-Chen/f994648993eeeebb64ae678f2d50f8d8a9194a40",
    "https://wjaets.com/content/integrating-data-engineering-and-mlops-scalable-and-resilient-machine-learning-pipelines",
    "https://www.semanticscholar.org/paper/Industry-5.0-in-aircraft-production-and-MRO%3A-and-Moenck-Koch/a4a5a9b6828d42ba3de62402652f7f22e67a95ea",
    "https://www.sciencedirect.com/science/article/pii/S0166361520305340",
    "https://www.semanticscholar.org/paper/Industrial-Applications-of-AI-in-Aircraft-A-PRISMA-Bougault-Haddad/b05af35428fdb4660bbdcbe4c49c17ba3afa9925",
    "https://www.semanticscholar.org/paper/Agentic-Insight-Generation-in-VSM-Simulations-Selak-Krechel/3e3458f4839fa6d8fd3f064e6787e89b86d237d8",
    "https://www.semanticscholar.org/paper/Development-of-automation-and-artificial-technology-Tsuzuki/2c730d995c894ba3c4eef54ea29c9c76b0242e67",
    "https://www.semanticscholar.org/paper/Surrogate-Modelling-with-Deep-Learning-for-Assembly-Saadi-Bernier/9f0736462fd81a837d759b7c4008d0500be334a2",
    "https://www.semanticscholar.org/paper/RAG-Based-AI-Agents-for-Enterprise-Software-and-Zhao-Sun/c27d3248e95c6ff979476356358298d1216a43c9",
    "https://www.semanticscholar.org/paper/Insights-into-the-Development-Trends-of-Industrial-Lai-Junqi/93fea9892ac73a1c2907ddec9728ebea654dd128",
    "https://www.semanticscholar.org/paper/A-Review-of-Artificial-Intelligence-Techniques-in-Zachariades-Xavier/8d54361f5598b35d159f10daaf1761ebfa6fcbff",
    "https://www.semanticscholar.org/paper/Verification-and-Validation-of-LLM-RAG-for-Min-Budnik/dab84454a66ac53f4e1881535a1adb3fa95e6499",
    "https://www.semanticscholar.org/paper/When-Industry-meets-Trustworthy-AI%3A-A-Systematic-of-Vyhmeister-Casta%C3%B1%C3%A9/f6f9ab29950315da1b2b8b8efc92dab3af470545",
    "https://www.semanticscholar.org/paper/From-Efficiency-to-Innovation%3A-LLM-5.0-and-the-of-Gantayat-Kaur/2d0f67e2bcf4d3ed7274649606238c3ab474efd5",
]

# A follow-up question grounded on the first turn's MOM corpus.
MOM_FOLLOWUP_QUERY = "已有文献里多智能体协作的主流框架有哪些？请基于已有文献回答。"


# ---------------------------------------------------------------------------
# Scenario 1: MOM first turn — full pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mom_new_topic(inject_store: FileStore) -> None:
    """MOM 综述首轮：完整 pipeline（理解 → 大纲 → 搜索 → 抓取 → 生成）。

    验证 new_topic 意图、真实搜索检索量、抓取量、最终综述产物。
    """
    store = inject_store
    session = store.create_session("AI原生MOM综述")
    session_id = session["id"]

    events = await collect_turn_events(session_id, MOM_REVIEW_PROMPT)

    print("\n===== test_mom_new_topic SUMMARY =====")
    print("PROMPT:", MOM_REVIEW_PROMPT)
    print(format_summary_text(summarize_events(events)))
    print("======================================\n")

    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None, "缺少 literature_intent 事件"
    assert intent_ev["intent"] == "new_topic", (
        f"首轮应识别为 new_topic，实际为 {intent_ev['intent']}"
    )

    # 不应有未捕获异常
    uncaught = find_event(events, "_uncaught_exception")
    assert uncaught is None, f"不应有未捕获异常: {uncaught}"

    summary = summarize_events(events)
    print("[MOM首轮] 检索来源:", summary["search"]["source_counts"])
    print("[MOM首轮] hits_found:", summary["search"]["total_hits_found"])
    print("[MOM首轮] hits_taken:", summary["search"]["total_hits_taken"])
    print("[MOM首轮] 抓取 ok/failed:", summary["fetch"]["ok"], summary["fetch"]["failed"])
    print("[MOM首轮] 综述字数:", summary["artifact_chars"])

    # 搜索应产出至少一些命中（真实 API，放宽到 >=1 以容忍来源波动）
    assert summary["search"]["total_hits_found"] >= 1, (
        f"MOM 综述搜索应检索到至少 1 条命中，"
        f"实际 hits_found={summary['search']['total_hits_found']}"
    )

    # 应有 turn_end（pipeline 正常完成）
    assert summary["has_turn_end"], "MOM 首轮应有 turn_end 事件"


# ---------------------------------------------------------------------------
# Scenario 2: MOM first turn + corpus Q&A follow-up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mom_followup_query(inject_store: FileStore) -> None:
    """MOM 首轮建立 corpus → 第2轮基于 corpus 问答。

    第一轮 new_topic（完整 pipeline），第二轮 query_corpus（基于 corpus 回答）。
    验证多轮对话的意图路由和 corpus 传递。
    """
    store = inject_store
    session = store.create_session("MOM问答")
    session_id = session["id"]

    # --- 第一轮：MOM 综述（建立 corpus）---
    events1 = await collect_turn_events(session_id, MOM_REVIEW_PROMPT)

    print("\n===== test_mom_followup_query [TURN 1] SUMMARY =====")
    print("PROMPT:", MOM_REVIEW_PROMPT)
    print(format_summary_text(summarize_events(events1)))
    print("=====================================================\n")

    intent1 = find_event(events1, "literature_intent")
    assert intent1 is not None
    assert intent1["intent"] == "new_topic", (
        f"第一轮应识别为 new_topic，实际为 {intent1['intent']}"
    )
    assert find_event(events1, "_uncaught_exception") is None, (
        "第一轮不应有未捕获异常"
    )

    # --- 第二轮：基于 corpus 的问答 ---
    events2 = await collect_turn_events(session_id, MOM_FOLLOWUP_QUERY)

    print("\n===== test_mom_followup_query [TURN 2] SUMMARY =====")
    print("PROMPT:", MOM_FOLLOWUP_QUERY)
    print(format_summary_text(summarize_events(events2)))
    print("=====================================================\n")

    intent2 = find_event(events2, "literature_intent")
    assert intent2 is not None, "第二轮应有 literature_intent 事件"
    assert intent2["intent"] == "query_corpus", (
        f"第二轮应识别为 query_corpus（有 corpus + 问句），"
        f"实际为 {intent2['intent']}"
    )
    assert find_event(events2, "_uncaught_exception") is None, (
        "第二轮不应有未捕获异常"
    )

    # query_corpus 应跳过搜索
    assert intent2.get("skip_web_search") is True, (
        "query_corpus 应跳过搜索"
    )


# ---------------------------------------------------------------------------
# Scenario 3: Submit reference URLs (append_urls)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_ref_list_urls(inject_seeded_store: FileStore) -> None:
    """提交 ref-list 前 15 个 URL：append_urls 意图，跳过搜索，直接抓取。

    使用 inject_seeded_store（已有 corpus 的 session），使 extra_fetch_urls 被路由为
    append_urls。验证抓取阶段对真实 URL 的处理与引用抽取。
    """
    store = inject_seeded_store
    session_id = store._e2e_session_id  # type: ignore[attr-defined]

    events = await collect_turn_events(
        session_id,
        "补充这些参考文献",
        extra_fetch_urls=REF_LIST_URLS_TOP15,
    )

    print("\n===== test_append_ref_list_urls SUMMARY =====")
    print("URLs:", len(REF_LIST_URLS_TOP15))
    print(format_summary_text(summarize_events(events)))
    print("=============================================\n")

    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None
    assert intent_ev["intent"] == "append_urls", (
        f"提交 URL 应识别为 append_urls，实际为 {intent_ev['intent']}"
    )
    assert intent_ev.get("skip_web_search") is True, (
        "append_urls 应跳过搜索"
    )

    # 不应有未捕获异常
    assert find_event(events, "_uncaught_exception") is None, (
        "URL 提交不应产生未捕获异常"
    )

    summary = summarize_events(events)
    print("[URL提交] 抓取 ok/failed/skipped:",
          summary["fetch"]["ok"], summary["fetch"]["failed"], summary["fetch"]["skipped"])
    print("[URL提交] 抓取总数:", summary["fetch"]["total"])

    # 抓取总数应等于提交的 URL 数（15），即使部分失败
    assert summary["fetch"]["total"] == len(REF_LIST_URLS_TOP15), (
        f"应尝试抓取 {len(REF_LIST_URLS_TOP15)} 个 URL，"
        f"实际 fetch.total={summary['fetch']['total']}"
    )

    # 应有至少部分抓取成功（真实 URL，放宽到 >=1）
    assert summary["fetch"]["ok"] >= 1, (
        f"应至少抓取成功 1 个 URL，实际 ok={summary['fetch']['ok']}"
    )
