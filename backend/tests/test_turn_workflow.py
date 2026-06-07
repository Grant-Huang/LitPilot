"""Tests for persisted turn_workflow meta."""
from __future__ import annotations

from app.agents.turn_workflow import build_turn_workflow_meta


def test_build_turn_workflow_meta_search_summary_from_stats() -> None:
    trace = {
        "stages": [
            {"name": "文献检索", "state": "done"},
            {"name": "抓取网页", "state": "done"},
            {"name": "综述生成", "state": "done"},
        ],
        "tools": [
            {"name": "web_search", "status": "done", "id": "tc_a"},
            {"name": "web_search", "status": "done", "id": "tc_b"},
            {"name": "web_fetch", "status": "done", "id": "tc_c"},
            {"name": "web_fetch", "status": "error", "id": "tc_d"},
        ],
        "literatureStats": {"searchMerged": 12, "searchPasses": 2},
    }
    meta = build_turn_workflow_meta(trace, intent="new_topic")
    search = next(c for c in meta["cards"] if c["type"] == "search")
    fetch = next(c for c in meta["cards"] if c["type"] == "fetch")
    assert search["summary"] == "纳入 12 篇"
    assert fetch["summary"] == "1 篇 · 1 失败"
    assert "纳入 12 篇" in meta["summary"]
    assert "综述已生成" in meta["summary"]


def test_build_turn_workflow_meta_brief_subtopics() -> None:
    trace = {
        "stages": [{"name": "理解研究问题", "state": "done"}],
        "tools": [],
    }
    meta = build_turn_workflow_meta(
        trace,
        intent="new_topic",
        process_text="四 aspect brief",
        subtopic_count=4,
    )
    understand = next(c for c in meta["cards"] if c["type"] == "understand")
    assert understand["summary"] == "4 个子主题"
