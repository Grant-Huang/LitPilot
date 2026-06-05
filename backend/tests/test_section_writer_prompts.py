"""Tests for section writer prompt labels."""
from __future__ import annotations

from app.agents.literature_section_writer import build_section_user_prompt
from app.agents.prompt_registry import (
    DEFAULT_SECTION_REFINE_SYSTEM,
    DEFAULT_SECTION_SYSTEM,
)
from app.schemas.literature_outline import LiteratureOutline, OutlineSection


def test_section_system_prompt_uses_mounted_materials_guide() -> None:
    assert "[网页材料]" in DEFAULT_SECTION_SYSTEM
    assert "【挂载文献】" in DEFAULT_SECTION_SYSTEM
    assert DEFAULT_SECTION_REFINE_SYSTEM.count("[网页材料]") >= 1


def test_section_user_prompt_labels_mounted_block() -> None:
    outline = LiteratureOutline(
        topic="AI MES",
        research_questions=["RQ1"],
        sections=[
            OutlineSection(
                id="sec-1",
                number=1,
                title="背景",
                desc="概述领域",
                mounted_paper_ids=[],
            )
        ],
    )
    section = outline.sections[0]
    out = build_section_user_prompt(outline, section, "（暂无挂载）")
    assert "【挂载文献】" in out
    assert "[网页材料]" in out
