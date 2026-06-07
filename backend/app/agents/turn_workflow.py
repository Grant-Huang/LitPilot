"""Build persisted turn_workflow summary for assistant message meta (v2)."""
from __future__ import annotations

from typing import Any

PHASE_LABELS: dict[str, str] = {
    "understand": "理解研究问题",
    "brief": "Brief 评估",
    "search": "子主题检索",
    "filter": "子主题过滤",
    "fetch": "抓取全文",
    "generate": "分章综述",
    "matrix": "文献矩阵",
    "corpus_qa": "语料问答",
}

TOOL_PHASE: dict[str, str] = {
    "web_search": "search",
    "web_fetch": "fetch",
    "extract_citation": "cite",
    "cite_extract": "cite",
}


def stage_to_phase(name: str) -> str | None:
    n = (name or "").strip()
    if not n:
        return None
    if "理解" in n:
        return "understand"
    if "Brief" in n or "brief" in n.lower():
        return "brief"
    if "过滤" in n or "筛选" in n:
        return "filter"
    if "检索" in n:
        return "search"
    if "抓取" in n:
        return "fetch"
    if "矩阵" in n:
        return "matrix"
    if "问答" in n:
        return "corpus_qa"
    if "撰写" in n or "综述" in n or "生成" in n:
        return "generate"
    if "完成" in n:
        return None
    return None


def record_literature_stats(trace: dict[str, Any], **kwargs: Any) -> None:
    stats = trace.setdefault("literatureStats", {})
    for key, value in kwargs.items():
        if value is not None:
            stats[key] = value


def _count_tools(tools: list[dict[str, Any]], name: str, status: str | None = None) -> int:
    n = 0
    for tool in tools:
        if str(tool.get("name") or "") != name:
            continue
        if status is not None and str(tool.get("status") or "") != status:
            continue
        n += 1
    return n


def _card_summary(
    phase: str,
    *,
    tools: list[dict[str, Any]],
    stats: dict[str, Any],
    subtopic_count: int = 0,
) -> str:
    if phase == "search":
        merged = stats.get("searchMerged")
        if isinstance(merged, int):
            return f"纳入 {merged} 篇"
        passes = _count_tools(tools, "web_search", "done")
        return f"{passes} 轮检索" if passes else "已完成"
    if phase == "filter":
        return "已完成"
    if phase == "fetch":
        ok = _count_tools(tools, "web_fetch", "done")
        failed = _count_tools(tools, "web_fetch", "error")
        if ok or failed:
            return f"{ok} 篇 · {failed} 失败" if failed else f"{ok} 篇"
        total = stats.get("fetchQueueTotal")
        if isinstance(total, int) and total > 0:
            return f"{total} 篇"
        return "已完成"
    if phase == "generate":
        return "综述已生成"
    if phase == "matrix":
        return "矩阵已生成"
    if phase in ("understand", "brief") and subtopic_count > 0:
        return f"{subtopic_count} 个子主题"
    return "已完成"


def build_turn_workflow_meta(
    execution_trace: dict[str, Any],
    *,
    intent: str,
    summary: str = "",
    process_text: str = "",
    chat_text: str = "",
    subtopic_count: int = 0,
) -> dict[str, Any]:
    """Summarize execution_trace into turn_workflow for msg_meta."""
    cards: list[dict[str, Any]] = []
    stats = dict(execution_trace.get("literatureStats") or {})
    tools = [
        t for t in (execution_trace.get("tools") or []) if isinstance(t, dict)
    ]

    for stage in execution_trace.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        phase = stage_to_phase(str(stage.get("name") or ""))
        if not phase:
            continue
        cards.append(
            {
                "type": phase,
                "title": str(stage.get("name") or PHASE_LABELS.get(phase, phase)),
                "state": str(stage.get("state") or "done"),
                "steps": [],
            }
        )

    if process_text.strip():
        cards.insert(
            0 if not cards else min(1, len(cards)),
            {
                "type": "brief",
                "title": PHASE_LABELS["brief"],
                "state": "done",
                "body": process_text.strip()[:4000],
                "steps": [],
            },
        )

    if chat_text.strip() and intent == "query_corpus":
        cards.append(
            {
                "type": "corpus_qa",
                "title": PHASE_LABELS["corpus_qa"],
                "state": "done",
                "body": chat_text.strip()[:800],
                "steps": [],
            }
        )

    phase_tools: dict[str, list[dict[str, Any]]] = {k: [] for k in PHASE_LABELS}
    for tool in tools:
        name = str(tool.get("name") or "")
        phase = TOOL_PHASE.get(name)
        if phase:
            phase_tools.setdefault(phase, []).append(tool)

    seen_types: set[str] = set()
    for card in cards:
        ctype = str(card.get("type") or "")
        seen_types.add(ctype)
        card["summary"] = _card_summary(
            ctype,
            tools=phase_tools.get(ctype, []),
            stats=stats,
            subtopic_count=subtopic_count,
        )

    headline_parts: list[str] = []
    search_passes = _count_tools(tools, "web_search", "done")
    if search_passes:
        headline_parts.append(f"检索 {search_passes} 轮")
    merged = stats.get("searchMerged")
    if isinstance(merged, int):
        headline_parts.append(f"纳入 {merged} 篇")
    fetch_ok = _count_tools(tools, "web_fetch", "done")
    if fetch_ok:
        headline_parts.append(f"抓取 {fetch_ok} 篇")
    fetch_failed = _count_tools(tools, "web_fetch", "error")
    if fetch_failed:
        headline_parts.append(f"{fetch_failed} 篇失败")
    if any(c.get("type") == "generate" for c in cards):
        headline_parts.append("综述已生成")

    return {
        "intent": intent,
        "summary": summary or (
            " · ".join(headline_parts[:5]) if headline_parts else _default_summary(cards, intent)
        ),
        "cards": cards,
    }


def _default_summary(cards: list[dict[str, Any]], intent: str) -> str:
    summaries = [
        str(c.get("summary") or c.get("title") or "")
        for c in cards
        if c.get("summary") or c.get("title")
    ]
    if summaries:
        return " · ".join(summaries[:4])
    titles = [str(c.get("title") or "") for c in cards if c.get("title")]
    if not titles:
        return intent
    return " · ".join(titles[:4])
