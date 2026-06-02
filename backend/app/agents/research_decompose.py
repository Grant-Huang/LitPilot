"""Decompose user brief into research sub-topics (M2)."""
from __future__ import annotations

import re
import uuid

from app.schemas.literature_outline import ResearchSubTopic

_CN_ENUM = re.compile(
    r"(?:^|\n)\s*"
    r"(?:其[一二三四五六七八]|第[一二三四五六七八]|(?:\(?[1-9]\d*\)?[\.、．]))"
    r"[，,、:\s]*"
    r"(.+?)(?=(?:\n\s*(?:其[一二三四五六七八]|第[一二三四五六七八]|(?:\(?[1-9]\d*\)?[\.、．]))|\Z))",
    re.S,
)


def _slug_id(prefix: str = "thread") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _clean_chunk(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"[。；;]+$", "", t)
    return t.strip()


def decompose_research_brief(user_message: str, *, base_query: str = "") -> list[ResearchSubTopic]:
    """Rule-based split for numbered/multi-aspect briefs (其一…其四 / 1. …)."""
    msg = (user_message or "").strip()
    if not msg:
        return []

    chunks: list[str] = []
    for m in _CN_ENUM.finditer(msg):
        body = _clean_chunk(m.group(1))
        if len(body) >= 8:
            chunks.append(body)

    if len(chunks) < 2:
        return []

    topics: list[ResearchSubTopic] = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.split("，")[0].split(",")[0].strip()
        if len(title) > 48:
            title = title[:45] + "…"
        search_q = base_query.strip()
        if search_q and title.lower() not in search_q.lower():
            search_q = f"{search_q} {title}"
        else:
            search_q = search_q or title
        topics.append(
            ResearchSubTopic(
                id=_slug_id(f"thread{i}"),
                title=title or f"子主题 {i}",
                description=chunk,
                search_query=search_q[:200],
            )
        )
    return topics


def default_single_sub_topic(user_message: str, search_query: str) -> ResearchSubTopic:
    topic = (search_query or user_message or "文献综述").strip()[:120]
    return ResearchSubTopic(
        id=_slug_id("thread"),
        title=topic[:48],
        description=user_message.strip()[:500],
        search_query=topic[:200],
    )
