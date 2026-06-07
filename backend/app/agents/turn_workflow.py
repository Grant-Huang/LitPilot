"""Build persisted turn_workflow summary for assistant message meta."""
from __future__ import annotations

from typing import Any

PHASE_LABELS: dict[str, str] = {
    "understand": "理解研究问题",
    "brief": "Brief 评估",
    "search": "文献检索",
    "fetch": "抓取全文",
    "cite": "引用抽取",
    "attributes": "文献结构化",
    "outline": "大纲规划",
    "generate": "综述生成",
    "matrix": "文献矩阵",
    "revise": "章节修订",
    "corpus_qa": "语料问答",
    "clarify": "等待澄清",
}


def stage_to_phase(name: str) -> str | None:
    n = (name or "").strip()
    if not n:
        return None
    if "理解" in n:
        return "understand"
    if "澄清" in n or "等待" in n:
        return "clarify"
    if "检索" in n or "相关性" in n:
        return "search"
    if "抓取" in n:
        return "fetch"
    if "引用" in n:
        return "cite"
    if "结构化" in n:
        return "attributes"
    if "大纲" in n:
        return "outline"
    if "矩阵" in n:
        return "matrix"
    if "问答" in n:
        return "corpus_qa"
    if "撰写" in n or "综述" in n:
        return "generate"
    if "完成" in n:
        return None
    return None


def build_turn_workflow_meta(
    execution_trace: dict[str, Any],
    *,
    intent: str,
    summary: str = "",
    process_text: str = "",
    chat_text: str = "",
) -> dict[str, Any]:
    """Summarize execution_trace + inline text into turn_workflow for msg_meta."""
    cards: list[dict[str, Any]] = []
    phase_tools: dict[str, list[dict[str, Any]]] = {k: [] for k in PHASE_LABELS}

    active_phase = "understand"
    for stage in execution_trace.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        phase = stage_to_phase(str(stage.get("name") or ""))
        if phase:
            active_phase = phase
        cards.append(
            {
                "type": phase or active_phase,
                "title": str(stage.get("name") or ""),
                "state": str(stage.get("state") or "done"),
            }
        )

    for tool in execution_trace.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "")
        step = {
            "kind": "tool",
            "name": name,
            "status": str(tool.get("status") or "done"),
            "title": name,
        }
        phase_tools[active_phase].append(step)

    if process_text.strip():
        cards.insert(
            1 if cards else 0,
            {
                "type": "brief",
                "title": PHASE_LABELS["brief"],
                "state": "done",
                "body": process_text.strip()[:4000],
            },
        )

    if chat_text.strip():
        if intent == "query_corpus":
            cards.append(
                {
                    "type": "corpus_qa",
                    "title": PHASE_LABELS["corpus_qa"],
                    "state": "done",
                    "body": chat_text.strip()[:800],
                }
            )
        elif intent in ("clarify", "plan_confirm") or any(
            c.get("type") == "clarify" for c in cards
        ):
            for card in cards:
                if card.get("type") == "clarify":
                    card["body"] = chat_text.strip()[:800]
                    card["locked"] = True
                    break
            else:
                cards.append(
                    {
                        "type": "clarify",
                        "title": PHASE_LABELS["clarify"],
                        "state": "done",
                        "body": chat_text.strip()[:800],
                        "locked": True,
                    }
                )

    clarifying = any(
        c.get("type") == "clarify" and (c.get("locked") or c.get("state") != "done")
        for c in cards
    )

    return {
        "intent": intent,
        "summary": summary or _default_summary(cards, intent),
        "cards": cards,
        "clarifying": clarifying,
    }


def _default_summary(cards: list[dict[str, Any]], intent: str) -> str:
    titles = [str(c.get("title") or "") for c in cards if c.get("title")]
    if not titles:
        return intent
    return " · ".join(titles[:4])
