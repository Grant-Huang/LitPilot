"""Subtopic plan and outline (v2: subtopic = chapter)."""
from __future__ import annotations

from typing import Any

from app.agents.research_decompose import default_single_sub_topic, decompose_research_brief
from app.agents.search_aspects import SearchAspect, aspects_to_sub_topics
from app.agents.literature_router import TOPIC_LABEL_MAX, clamp_search_query
from app.schemas.literature_outline import LiteratureOutline, OutlineSection, ResearchSubTopic

_INTRO_SECTION = OutlineSection(
    id="sec-intro",
    number="0",
    title="导言与研究问题",
    desc="阐明背景、范围与核心研究问题（RQ），不展开细节论述。",
)
_CONCLUSION_SECTION = OutlineSection(
    id="sec-conclusion",
    number="99",
    title="综合讨论与未来方向",
    desc="跨章节归纳共识、张力、空白与工程迁移启示。",
)


def _outline_topic_label(
    *,
    session_title: str,
    search_query: str,
    user_message: str,
) -> str:
    return clamp_search_query(
        session_title or search_query or user_message,
        max_len=TOPIC_LABEL_MAX,
        fallback=user_message,
    )


def build_outline_from_sub_topics(
    *,
    topic: str,
    sub_topics: list[ResearchSubTopic],
) -> LiteratureOutline:
    import uuid

    sections: list[OutlineSection] = [_INTRO_SECTION]
    for i, st in enumerate(sub_topics, start=1):
        sections.append(
            OutlineSection(
                id=f"sec-{uuid.uuid4().hex[:8]}",
                number=str(i),
                title=st.title,
                desc=st.description,
                sub_topic_id=st.id,
            )
        )
    sections.append(_CONCLUSION_SECTION)
    rqs = [st.title for st in sub_topics] if sub_topics else [topic]
    return LiteratureOutline(
        topic=topic,
        research_questions=rqs[:6],
        sub_topics=sub_topics,
        sections=sections,
        status="draft",
    )


def build_subtopic_plan(
    *,
    user_message: str,
    search_query: str,
    session_title: str = "",
    search_aspects: list[SearchAspect] | None = None,
    stored_outline: LiteratureOutline | None = None,
    intent: str = "new_topic",
) -> tuple[LiteratureOutline, list[ResearchSubTopic]]:
    """Always returns subtopic-driven outline (v2 single path)."""
    if intent == "review_refine" and stored_outline and stored_outline.sections:
        return stored_outline, list(stored_outline.sub_topics)

    if search_aspects and len(search_aspects) >= 1:
        sub_topics = aspects_to_sub_topics(search_aspects)
    else:
        sub_topics = decompose_research_brief(user_message, base_query=search_query)
    if not sub_topics:
        sub_topics = [default_single_sub_topic(user_message, search_query)]

    topic = _outline_topic_label(
        session_title=session_title,
        search_query=search_query,
        user_message=user_message,
    )
    outline = build_outline_from_sub_topics(topic=topic, sub_topics=sub_topics)
    return outline, sub_topics


def mount_papers_by_subtopic_tags(
    outline: LiteratureOutline,
    papers: list[dict[str, Any]],
) -> LiteratureOutline:
    """Mount papers onto sections via subtopic_tags."""
    by_subtopic: dict[str, list[str]] = {}
    for p in papers:
        if not p.get("cite_in_review", True):
            continue
        url = str(p.get("url") or "")
        if not url:
            continue
        for tag in p.get("subtopic_tags") or []:
            sid = str(tag).strip()
            if sid:
                by_subtopic.setdefault(sid, []).append(url)

    for sec in outline.sections:
        if not sec.sub_topic_id:
            continue
        urls = by_subtopic.get(sec.sub_topic_id, [])
        sec.mounted_paper_ids = list(dict.fromkeys(urls))
    return outline
