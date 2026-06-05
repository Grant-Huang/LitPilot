"""Section-by-section review generation (M2)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.schemas.literature_outline import LiteratureOutline, OutlineSection
from app.schemas.paper_record import PaperRecord
from app.agents.prompt_registry import (
    DEFAULT_SECTION_REFINE_SYSTEM as SECTION_REFINE_SYSTEM,
    DEFAULT_SECTION_SYSTEM as SECTION_SYSTEM,
)
from app.agents.prompt_settings import get_section_system_prompt
from app.llm.base import LLMMessage


def _papers_by_id(paper_index: list[dict[str, Any]]) -> dict[str, PaperRecord]:
    out: dict[str, PaperRecord] = {}
    for raw in paper_index:
        if isinstance(raw, dict):
            rec = PaperRecord.from_dict(raw)
            if rec.paper_id:
                out[rec.paper_id] = rec
    return out


def format_section_materials(
    section: OutlineSection,
    paper_by_id: dict[str, PaperRecord],
) -> str:
    blocks: list[str] = []
    for pid in section.mounted_paper_ids:
        paper = paper_by_id.get(pid)
        if not paper:
            continue
        attri = paper.attri or {}
        blocks.append(
            "\n".join(
                [
                    f"### {paper.title or paper.url}",
                    f"- 问题：{attri.get('problem') or '—'}",
                    f"- 方法：{attri.get('method') or '—'}",
                    f"- 结论：{attri.get('findings') or '—'}",
                ]
            )
        )
    return "\n\n".join(blocks) if blocks else "（本章暂无专属挂载文献，请基于全局材料谨慎归纳。）"


def build_section_user_prompt(
    outline: LiteratureOutline,
    section: OutlineSection,
    materials: str,
    *,
    prior_excerpt: str = "",
    prior_section_body: str = "",
    gen_directives: str = "",
    writing_emphasis: str = "",
    is_refine: bool = False,
) -> str:
    rq = "；".join(outline.research_questions[:4])
    parts = [
        f"【综述主题】{outline.topic}",
        f"【研究问题】{rq}",
        f"【当前章节】{section.number}. {section.title}",
        f"【章节要求】{section.desc}",
    ]
    if is_refine and prior_section_body.strip():
        parts.append(
            f"【上一版本章稿（在此基础上修订）】\n{prior_section_body.strip()[-4000:]}"
        )
    if writing_emphasis.strip() and not is_refine:
        parts.append(f"【本节侧重（规划生成）】{writing_emphasis.strip()}")
    if gen_directives.strip():
        label = "【修订要求】" if is_refine else "【写作指令】"
        parts.append(f"{label}{gen_directives.strip()}")
    if prior_excerpt.strip():
        parts.append(f"【前文摘要（保持衔接，勿重复）】\n{prior_excerpt[-800:]}")
    parts.append(
        "【挂载文献】（结构化摘要，源于 [网页材料] 流水线；与检索后端无关）\n"
        + materials
    )
    verb = "修订" if is_refine else "撰写"
    parts.append(f"请{verb}本章 Markdown 正文（以 ### 小节标题 开头，不要输出一级 # 标题）。")
    return "\n\n".join(parts)


async def stream_section_generate(
    llm,
    *,
    outline: LiteratureOutline,
    section: OutlineSection,
    paper_index: list[dict[str, Any]],
    prior_excerpt: str = "",
    prior_section_body: str = "",
    gen_directives: str = "",
    writing_emphasis: str = "",
    is_refine: bool = False,
    max_tokens: int = 1200,
) -> AsyncIterator[str]:
    paper_by_id = _papers_by_id(paper_index)
    materials = format_section_materials(section, paper_by_id)
    prompt = build_section_user_prompt(
        outline,
        section,
        materials,
        prior_excerpt=prior_excerpt,
        prior_section_body=prior_section_body,
        gen_directives=gen_directives,
        writing_emphasis=writing_emphasis,
        is_refine=is_refine,
    )
    system = await get_section_system_prompt(
        is_refine=is_refine and bool(prior_section_body.strip())
    )
    async for chunk in llm.chat_stream(
        [LLMMessage(role="user", content=prompt)],
        system=system,
        max_tokens=max_tokens,
        temperature=0.35,
    ):
        if chunk:
            yield chunk


def stitch_review_sections(parts: list[tuple[OutlineSection, str]]) -> str:
    """Merge section bodies into one markdown document."""
    lines: list[str] = []
    for section, body in parts:
        body = (body or "").strip()
        if not body:
            continue
        if section.id == "sec-intro":
            lines.append(f"# {section.title}\n\n{body}")
        elif section.id == "sec-conclusion":
            lines.append(f"## {section.title}\n\n{body}")
        else:
            if not body.lstrip().startswith("#"):
                lines.append(f"## {section.number}. {section.title}\n\n{body}")
            else:
                lines.append(body)
    return "\n\n".join(lines).strip() + "\n"
