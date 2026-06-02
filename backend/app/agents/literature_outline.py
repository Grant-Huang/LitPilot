"""Outline generation and paper mounting (M2)."""
from __future__ import annotations

import re
import uuid
from typing import Any

from app.agents.research_decompose import default_single_sub_topic, decompose_research_brief
from app.schemas.literature_outline import LiteratureOutline, OutlineSection, ResearchSubTopic
from app.schemas.paper_record import PaperRecord

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


def _section_id(prefix: str = "sec") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def build_outline_from_sub_topics(
    *,
    topic: str,
    sub_topics: list[ResearchSubTopic],
    user_message: str = "",
) -> LiteratureOutline:
    sections: list[OutlineSection] = [_INTRO_SECTION]
    for i, st in enumerate(sub_topics, start=1):
        sections.append(
            OutlineSection(
                id=_section_id(),
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


def prepare_outline(
    *,
    user_message: str,
    search_query: str,
    session_title: str = "",
) -> LiteratureOutline:
    sub_topics = decompose_research_brief(user_message, base_query=search_query)
    topic = (session_title or search_query or user_message).strip()[:120]
    if not sub_topics:
        sub_topics = [default_single_sub_topic(user_message, search_query)]
    return build_outline_from_sub_topics(
        topic=topic,
        sub_topics=sub_topics,
        user_message=user_message,
    )


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[\s,，、;；:：/\\\-—]+", (text or "").lower())
    return {p for p in parts if len(p) >= 2}


def _score_paper_for_section(paper: PaperRecord, section: OutlineSection) -> float:
    title_tokens = _tokenize(section.title)
    desc_tokens = _tokenize(section.desc)
    keys = title_tokens | desc_tokens
    if not keys:
        return 0.0
    attri = paper.attri or {}
    blob = " ".join(
        [
            paper.title,
            str(attri.get("problem") or ""),
            str(attri.get("method") or ""),
            str(attri.get("findings") or ""),
            " ".join(attri.get("keywords") or []),
        ]
    ).lower()
    if not blob.strip():
        blob = paper.title.lower()
    hit = sum(1 for k in keys if k in blob)
    return hit / max(len(keys), 1)


def mount_papers_to_outline(
    outline: LiteratureOutline,
    paper_index: list[dict[str, Any]],
    *,
    max_per_section: int = 8,
) -> LiteratureOutline:
    papers = [PaperRecord.from_dict(p) for p in paper_index if isinstance(p, dict)]
    body_sections = [
        s for s in outline.sections if s.id not in ("sec-intro", "sec-conclusion")
    ]
    assigned: set[str] = set()

    for section in body_sections:
        scored: list[tuple[float, PaperRecord]] = []
        for paper in papers:
            if not paper.paper_id:
                continue
            scored.append((_score_paper_for_section(paper, section), paper))
        scored.sort(key=lambda x: (-x[0], x[1].title))
        section.mounted_paper_ids = []
        section.mount_hints = []
        for score, paper in scored[: max_per_section * 2]:
            if score <= 0 and section.mounted_paper_ids:
                continue
            if paper.paper_id in assigned and len(section.mounted_paper_ids) >= 2:
                continue
            if len(section.mounted_paper_ids) >= max_per_section:
                break
            section.mounted_paper_ids.append(paper.paper_id)
            assigned.add(paper.paper_id)
            hint = str((paper.attri or {}).get("findings") or (paper.attri or {}).get("problem") or paper.title)
            section.mount_hints.append(
                {"paper_id": paper.paper_id, "key_info": hint[:300]}
            )

    for section in outline.sections:
        if section.id in ("sec-intro", "sec-conclusion"):
            section.mounted_paper_ids = []
            section.mount_hints = []
    outline.status = "confirmed"
    return outline
