"""Prompt helpers for literature synthesis matrix generation."""
from __future__ import annotations

from app.agents.prompt_registry import DEFAULT_SYNTHESIS_MATRIX_SYSTEM
from app.agents.review_prompt import build_multi_source_user_prompt

MAX_MATRIX_SYSTEM_PROMPT_LEN = 8_000

SYNTHESIS_MATRIX_LANG = "literature-matrix+markdown"


def build_synthesis_matrix_system_prompt(
    *,
    initial_query: str = "",
    gen_directives: str = "",
    base_template: str | None = None,
) -> str:
    parts = [base_template or DEFAULT_SYNTHESIS_MATRIX_SYSTEM]
    directives: list[str] = []
    if initial_query.strip():
        directives.append(f"研究主题：{initial_query.strip()}")
    if gen_directives.strip():
        directives.append(f"用户矩阵要求：{gen_directives.strip()}")
    if directives:
        parts.append("【本轮矩阵生成指令（不得逐字写入正文）】")
        parts.extend(f"- {line}" for line in directives)
    out = "\n\n".join(parts)
    return out[:MAX_MATRIX_SYSTEM_PROMPT_LEN]


def build_synthesis_matrix_user_prompt(context_block: str) -> str:
    return build_multi_source_user_prompt(
        "请基于下列【多源材料】生成 Markdown 文献综述矩阵（Synthesis Matrix）。",
        context_block,
    )
