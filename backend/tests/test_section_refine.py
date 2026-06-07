"""Tests for section-level refine (P0)."""
from __future__ import annotations

from app.agents.literature_outline import build_subtopic_plan
from app.agents.literature_section_writer import stitch_review_sections
from app.agents.section_refine import (
    build_section_refine_plan,
    extract_section_bodies_from_review,
    parse_refine_target_section_ids,
)

MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，及其统一的工程整合框架。
其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"""


def _sample_outline():
    outline, _ = build_subtopic_plan(
        user_message=MOM_BRIEF,
        search_query="AI-native MOM",
        session_title="AI MOM",
        intent="new_topic",
    )
    return outline


def test_parse_refine_second_chapter() -> None:
    outline = _sample_outline()
    body = [s for s in outline.sections if s.sub_topic_id]
    assert len(body) >= 2
    ids = parse_refine_target_section_ids("请只重写第二章，改为表格对比", outline)
    assert ids is not None
    assert ids[0] == body[1].id


def test_parse_refine_aspect_er() -> None:
    outline = _sample_outline()
    body = [s for s in outline.sections if s.sub_topic_id]
    ids = parse_refine_target_section_ids("重写其二，其余章节保留", outline)
    assert ids is not None
    assert body[1].id in ids


def test_extract_and_partial_plan() -> None:
    outline = _sample_outline()
    parts = []
    for sec in outline.sections:
        if sec.id == "sec-intro":
            parts.append((sec, "导言正文。"))
        elif sec.id == "sec-conclusion":
            parts.append((sec, "结论正文。"))
        else:
            parts.append((sec, f"{sec.title} 的详细论述。"))
    review = stitch_review_sections(parts)
    bodies = extract_section_bodies_from_review(review, outline)
    assert len(bodies) >= 3

    plan = build_section_refine_plan(
        user_message="只重写第二章",
        outline=outline,
        prior_review_text=review,
        gen_directives="增加表格",
    )
    assert plan.target_section_ids is not None
    assert plan.should_regenerate(plan.target_section_ids[0])
    body_secs = [s for s in outline.sections if s.sub_topic_id]
    assert not plan.should_regenerate(body_secs[0].id)
