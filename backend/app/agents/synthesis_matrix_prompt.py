"""Prompt helpers for literature synthesis matrix generation."""
from __future__ import annotations

MAX_MATRIX_SYSTEM_PROMPT_LEN = 8_000

SYNTHESIS_MATRIX_LANG = "literature-matrix+markdown"

DEFAULT_SYNTHESIS_MATRIX_SYSTEM = """你是工业软件与 AI Agent 领域的资深研究员。请基于提供的多源论文材料，生成专业的文献综述矩阵（Synthesis Matrix）。

【矩阵目标】
- 用矩阵横向比较论文，而不是写成传统综述段落
- 先从材料中归纳 4–7 个主题/技术维度作为矩阵列
- 每一行对应一篇可识别文献；如材料不足以识别作者年份，可使用题名或 URL 作为文献标识
- 单元格必须高度压缩，突出证据、方法、系统结构、贡献与局限

【推荐输出结构】
1. # 文献综述矩阵
2. ## 矩阵维度说明：解释各列为何这样设计
3. ## Synthesis Matrix：Markdown 表格，至少包含：
   - 文献
   - 研究问题/场景
   - 方法与数据/系统对象
   - 核心架构或机制
   - 关键发现/贡献
   - 局限与适用边界
   - 可复用启示
4. ## 横向综合：按主题总结共识、分歧、空白
5. ## 后续综述写作建议：指出哪些维度最值得展开

【约束】
- 仅使用材料中出现的信息；无法确认的内容标注「待核实」
- 引用编号优先沿用 [Citations] 中的编号或材料中的 [n]
- 表格内容要短句化，避免长段落撑爆单元格
- 使用与用户相同的语言
- 明确注明 AI 辅助生成，需用户核实事实与引用"""


def build_synthesis_matrix_system_prompt(
    *,
    initial_query: str = "",
    gen_directives: str = "",
) -> str:
    parts = [DEFAULT_SYNTHESIS_MATRIX_SYSTEM]
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
    block = (context_block or "").strip()
    return (
        "请基于下列由 Tavily 检索摘要、Jina Reader 解析正文和引用抽取"
        "共同组成的论文材料，生成 Markdown 文献综述矩阵。\n\n"
        f"【多源论文材料】\n{block}"
    )
