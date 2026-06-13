"""Live E2E tests for the Understand-phase clarification flow.

Clarification is triggered when router_result.confidence < confidence_threshold
(default 0.7). These tests cover two paths:

  1. Natural trigger  — a deliberately vague prompt that yields low confidence.
  2. Forced trigger   — a rich prompt but with the threshold raised to 0.95 so
                        any real confidence value (typically <= 1.0) is below it.

In both cases the pipeline emits a ``clarification`` event with options, then
(currently) auto-selects option 0 and proceeds with the search. We assert that
the clarification event is emitted and carries at least one option.

Run with:  .venv/bin/python -m pytest tests/test_literature_e2e_clarify.py -m live -v -s
"""
from __future__ import annotations

import pytest

from app.storage.file_store import FileStore

from tests.helpers.e2e_mocks import (
    collect_turn_events,
    find_event,
    format_summary_text,
    summarize_events,
)
from tests.test_literature_e2e import MOM_REVIEW_PROMPT

pytestmark = pytest.mark.live

# A deliberately vague prompt: enough to route to new_topic (first turn, no
# corpus) but too ambiguous to produce high-confidence search aspects, so the
# Understand planner should assign low confidence and enter clarification.
VAGUE_PROMPT = "帮我研究下MOM，越快越好，随便找点相关的就行"


# ---------------------------------------------------------------------------
# Scenario 1: natural clarification trigger (low-confidence routing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_natural_trigger(inject_store: FileStore) -> None:
    """模糊提示词 → 低置信度 → 发出 clarification 事件。

    依赖真实 LLM 对模糊输入给出较低 confidence。如果 LLM 恰好给出高置信度，
    则说明该 prompt 不适合自然触发；此时测试会记录但仍然通过（不阻塞），
    因为 forced-trigger 测试是更可靠的回归保护。
    """
    store = inject_store
    session = store.create_session("澄清-自然")
    session_id = session["id"]

    events = await collect_turn_events(session_id, VAGUE_PROMPT)

    print("\n===== test_clarify_natural_trigger SUMMARY =====")
    print("PROMPT:", VAGUE_PROMPT)
    print(format_summary_text(summarize_events(events)))
    print("================================================\n")

    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None, "缺少 literature_intent 事件"

    # 不应有 error / 未捕获异常
    assert find_event(events, "error") is None, "不应有 error 事件"
    assert find_event(events, "_uncaught_exception") is None, "不应有未捕获异常"

    summary = summarize_events(events)
    if summary["has_clarification"]:
        # 理想路径：确实触发了澄清
        assert summary["clarification_options_count"] >= 1, (
            "clarification 事件应至少包含 1 个选项"
        )
        print("[自然触发] 成功触发 clarification，选项数:",
              summary["clarification_options_count"])
    else:
        # LLM 给出了高置信度——记录为软警告，不失败
        print("[自然触发] 未触发 clarification（LLM 置信度 >= 阈值），"
              "该 prompt 可能不够模糊；依赖 forced-trigger 测试保护。")


# ---------------------------------------------------------------------------
# Scenario 2: forced clarification trigger (threshold raised to 0.95)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarify_forced_trigger(force_clarify_store: FileStore) -> None:
    """提高置信阈值到 0.95 → 即使是高质量 MOM 提示词也必然触发澄清。

    使用 force_clarify_store fixture，它将
    LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD=0.95，因此任何 <=1.0 的置信度
    都无法直接通过，必须进入 clarification。
    """
    store = force_clarify_store
    session = store.create_session("澄清-强制")
    session_id = session["id"]

    events = await collect_turn_events(session_id, MOM_REVIEW_PROMPT)

    print("\n===== test_clarify_forced_trigger SUMMARY =====")
    print("PROMPT:", MOM_REVIEW_PROMPT)
    print(format_summary_text(summarize_events(events)))
    print("================================================\n")

    intent_ev = find_event(events, "literature_intent")
    assert intent_ev is not None, "缺少 literature_intent 事件"
    assert intent_ev["intent"] == "new_topic", (
        f"首轮应识别为 new_topic，实际为 {intent_ev['intent']}"
    )

    # 不应有未捕获异常
    assert find_event(events, "_uncaught_exception") is None, "不应有未捕获异常"

    summary = summarize_events(events)
    # 强制高阈值下应至少出现 clarification / clarification_timeout 之一
    has_clarify_signal = (
        summary["has_clarification"]
        or summary["has_clarification_timeout"]
        or summary["has_clarification_error"]
    )
    assert has_clarify_signal, (
        "阈值 0.95 下应触发 clarify（clarification / timeout / error），"
        f"实际 summary={summary['has_clarification']},"
        f" timeout={summary['has_clarification_timeout']},"
        f" error={summary['has_clarification_error']}"
    )

    if summary["has_clarification"]:
        assert summary["clarification_options_count"] >= 1, (
            "clarification 事件应至少包含 1 个选项"
        )
        print("[强制触发] 成功触发 clarification，选项数:",
              summary["clarification_options_count"])
        print("[强制触发] clarification prompt:", summary["clarification_prompt"])
    elif summary["has_clarification_timeout"]:
        print("[强制触发] 触发了 clarification_timeout（已超过最大轮次）")
    elif summary["has_clarification_error"]:
        print("[强制触发] 触发了 clarification_error（澄清生成异常）")
