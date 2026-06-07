"""Assign subtopic tags to library items (append_urls)."""
from __future__ import annotations

import json
from typing import Any

from app.agents.llm_json import parse_json_object
from app.library.subtopic_tags import normalize_subtopic_id
from app.llm.base import LLMMessage
from app.schemas.literature_outline import ResearchSubTopic

_TAG_SYSTEM = """根据文献标题/摘要与现有子主题列表，为每条文献分配 1–3 个最相关的 subtopic_id。
仅输出 JSON：{"tags": [{"index": 0, "subtopic_ids": ["st1"]}]}"""


async def tag_items_to_subtopics(
    items: list[dict[str, Any]],
    subtopics: list[ResearchSubTopic],
    *,
    llm: Any,
) -> list[list[str]]:
    if not items or not subtopics:
        return [[] for _ in items]
    st_lines = [
        f"- {st.id}: {st.title} ({st.search_query[:80]})" for st in subtopics
    ]
    item_lines = []
    for i, it in enumerate(items):
        title = str(it.get("title") or it.get("url") or "")
        snippet = str(it.get("snippet") or it.get("abstract") or "")[:300]
        item_lines.append(f"[{i}] {title}\n{snippet}")
    body = (
        "【子主题】\n"
        + "\n".join(st_lines)
        + "\n\n【文献】\n"
        + "\n".join(item_lines)
    )
    valid_ids = {normalize_subtopic_id(st.id) for st in subtopics}
    try:
        resp = await llm.chat(
            [LLMMessage(role="user", content=body)],
            system=_TAG_SYSTEM,
            max_tokens=400,
            temperature=0.0,
        )
        data = parse_json_object(resp.content or "")
        tags_raw = data.get("tags") or []
        out: list[list[str]] = [[] for _ in items]
        for row in tags_raw:
            if not isinstance(row, dict):
                continue
            idx = int(row.get("index", -1))
            if idx < 0 or idx >= len(items):
                continue
            ids = [
                normalize_subtopic_id(str(t))
                for t in (row.get("subtopic_ids") or [])
                if normalize_subtopic_id(str(t)) in valid_ids
            ]
            out[idx] = ids
        return out
    except (ValueError, json.JSONDecodeError, TypeError):
        return [[] for _ in items]
