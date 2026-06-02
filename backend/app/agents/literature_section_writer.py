"""Section-by-section review generation (M2)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.schemas.literature_outline import LiteratureOutline, OutlineSection
from app.schemas.paper_record import PaperRecord
from app.llm.base import LLMMessage

SECTION_SYSTEM = """你是学术文献综述助手。仅撰写指定章节正文（Markdown）。
要求：
- 只写当前章节，不要写其他章节标题
- 以维度对比组织内容，避免逐篇流水账
- 仅引用【挂载文献】中的事实；无法核实的标注「待核实」
- 语言与用户材料一致（中文或英文）
- 不要复述用户原始提问"""

SECTION_REFINE_SYSTEM = """你是学术文献综述助手。正在修订既有章节的某一版草稿。
要求：
- 只输出修订后的本章正文（Markdown），不要输出其他章节
- 在【上一版本章稿】基础上按【修订要求】修改；保留仍准确且符合要求的段落
- 未要求修改的部分尽量保留结构与论据；要求重写时则重新组织
- 以维度对比组织内容；仅引用【挂载文献】中的事实
- 不要复述用户原始提问"""


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
    if gen_directives.strip():
        label = "【修订要求】" if is_refine else "【写作指令】"
        parts.append(f"{label}{gen_directives.strip()}")
    if prior_excerpt.strip():
        parts.append(f"【前文摘要（保持衔接，勿重复）】\n{prior_excerpt[-800:]}")
    parts.append(f"【挂载文献】\n{materials}")
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
        is_refine=is_refine,
    )
    system = SECTION_REFINE_SYSTEM if is_refine and prior_section_body.strip() else SECTION_SYSTEM
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
