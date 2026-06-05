"""Configurable system prompt for literature review generation."""
from __future__ import annotations

_CITATION_FORMAT_LABELS = {
    "apa": "APA",
    "acm": "ACM",
}

MAX_REVIEW_SYSTEM_PROMPT_LEN = 12_000

MULTI_SOURCE_MATERIALS_HEADER = "【多源材料】"

MATERIAL_SECTIONS_GUIDE = """【材料分栏说明】分栏标签与检索/抓取后端无关（可能是 native、OpenAlex、Brave、Tavily 等）；只使用材料里实际出现的栏目：
- [web_search]：学术检索引擎返回的摘要与命中概况（本轮未做 web 检索时可能缺失）
- [网页材料]：对已选 URL/PDF 抓取并清洗后的正文摘录（标题为文献标识；标注抓取失败者仅能谨慎引用其检索摘要）
- [Citations]：从正文抽取、字段较完整的 {fmt_label} 参考文献条目

证据优先级：以 [网页材料] 与 [Citations] 为主要依据；[web_search] 仅作背景与线索，不得仅凭检索摘要下定论。材料不足处须明示局限，勿臆测。"""

SECTION_MOUNTED_MATERIALS_GUIDE = """【材料说明】用户消息中的【挂载文献】为本章大纲挂载论文的结构化摘要（问题/方法/结论），来源于流水线对 [网页材料] 的抓取与抽取，与检索后端无关。若无挂载文献，表示本章材料不足，只能谨慎归纳并标注「待核实」。不得超出所列字段编造事实。"""


def material_sections_guide(fmt_label: str = "参考文献") -> str:
    """Shared corpus label guide for review / matrix / Q&A prompts."""
    return MATERIAL_SECTIONS_GUIDE.format(fmt_label=fmt_label)


DEFAULT_REVIEW_SYSTEM_PROMPT = (
    "你是学术文献综述助手。仅依据用户消息中"
    + MULTI_SOURCE_MATERIALS_HEADER
    + "撰写结构化综述，不得用训练知识填补材料未出现的事实。\n\n"
    + MATERIAL_SECTIONS_GUIDE
    + """

【综述结构与各节内容标准】

一、研究背景与问题定位
- 阐明该领域的现实驱动力与技术/社会背景，说明为何此时此刻有必要开展综述
- 明确提出 2–3 个贯穿全文的核心研究问题（RQ），后续各节内容应围绕这些问题展开
- 简述综述范围的边界：涵盖哪类研究、排除哪类研究，以及为何如此划定

二、理论/概念框架（如材料支撑）
- 若材料中存在可抽象的分析框架，须先建立框架再展开综述，而非堆砌文献
- 框架应说明关键变量之间的逻辑关系（如因果链、调节/中介关系、层级结构），并指明该框架如何指导后续文献的分类与对比
- 若材料不足以支撑独立框架，则在「三、主要研究工作对比」节中内嵌分析维度

三、主要研究工作对比
- 按分析维度（而非按文献逐一罗列）组织内容；维度应从研究问题中自然导出
- 对比时须同时呈现：研究发现的共识、存在的矛盾或张力、各方法论路径的优劣
- 区分不同类型研究（如实证 vs. 概念性、定量 vs. 定性）并说明其对结论可靠性的影响
- 在节末给出阶段性小结，明确交代该维度上已知什么、尚不清楚什么，并用一句话呼应 RQ

四、研究空白与未来方向
- 空白须有据可查（指向具体文献或对比结果），而非泛泛而谈
- 区分两类空白：（1）已有研究但结论不一致；（2）完全缺乏实证或理论探讨
- 未来方向须具体：建议研究问题、适宜的方法论路径及其理由
- 如材料支撑，补充对实践者/管理者的启示

五、参考文献
- 格式严格遵循 {fmt_label} 规范
- 仅列 [Citations] 中可核实条目；无法核实的事实在正文中标注「待核实」

【通用写作标准】
- 综述的论证主线须始终与开篇研究问题保持对应
- 优先使用表格或维度对比呈现多文献的横向比较，避免流水式逐篇叙述
- 仅引用材料中出现的事实；不得编造作者、数据、方法细节或结论
- 使用与用户相同的语言（中文或英文）
- 正文不得复述、引用或逐字粘贴用户的原始提问与写作指令；直接从「一、研究背景与问题定位」起笔
- 文末注明本文由 AI 辅助生成，需用户自行核实所有事实与引用，不构成代写建议"""
)


def build_multi_source_user_prompt(
    intro: str,
    context_block: str,
    *,
    prior_excerpt: str = "",
    prior_header: str = "",
) -> str:
    """User message wrapper with unified 【多源材料】 block."""
    block = (context_block or "").strip()
    parts = [intro.strip()]
    if prior_excerpt.strip():
        header = (prior_header or "【参考上下文】").strip()
        parts.append(f"{header}\n" + prior_excerpt.strip()[-6000:])
    parts.append(f"{MULTI_SOURCE_MATERIALS_HEADER}\n{block}")
    return "\n\n".join(parts)


_TURN_DIRECTIVE_HEADER = """【本轮生成指令（仅供理解，不得写入正文）】"""


def default_review_system_prompt_template() -> str:
    """Default template with placeholders (for settings UI reset)."""
    return DEFAULT_REVIEW_SYSTEM_PROMPT


def citation_format_label(citation_format: str) -> str:
    return _fmt_label(citation_format)


def _fmt_label(citation_format: str) -> str:
    return _CITATION_FORMAT_LABELS.get(citation_format, "APA")


def build_review_system_prompt(
    citation_format: str,
    template: str | None = None,
) -> str:
    """Render review system prompt; invalid custom template falls back to default."""
    fmt = _fmt_label(citation_format)
    cf = (citation_format or "apa").strip().lower() or "apa"
    default = DEFAULT_REVIEW_SYSTEM_PROMPT.format(
        fmt_label=fmt,
        citation_format=cf,
    )
    raw = (template or "").strip()
    if not raw:
        return default
    try:
        return raw.format(fmt_label=fmt, citation_format=cf)
    except (KeyError, ValueError):
        return default


def build_review_turn_system_prompt(
    citation_format: str,
    template: str | None,
    *,
    initial_query: str = "",
    gen_constraints: list[str] | None = None,
    gen_directives: str = "",
    writing_emphasis: str = "",
    intent: str = "new_topic",
) -> str:
    """System prompt for one review generation turn (constraints stay out of user message)."""
    base = build_review_system_prompt(citation_format, template)
    parts = [base]
    directive_lines: list[str] = []
    if initial_query.strip():
        directive_lines.append(f"研究主题：{initial_query.strip()}")
    for c in gen_constraints or []:
        c = (c or "").strip()
        if c:
            directive_lines.append(f"写作要求：{c}")
    if writing_emphasis.strip():
        directive_lines.append(f"写作侧重：{writing_emphasis.strip()}")
    if gen_directives.strip() and intent == "refine_gen":
        directive_lines.append(f"本轮新增要求：{gen_directives.strip()}")
    if intent == "regen_only":
        directive_lines.append("请基于相同材料重新组织综述结构与论述。")
    if directive_lines:
        parts.append(_TURN_DIRECTIVE_HEADER)
        parts.extend(f"- {line}" for line in directive_lines)
    merged = "\n\n".join(parts)
    if len(merged) > MAX_REVIEW_SYSTEM_PROMPT_LEN:
        return merged[:MAX_REVIEW_SYSTEM_PROMPT_LEN]
    return merged


def build_review_materials_user_prompt(
    context_block: str,
    *,
    prior_review_excerpt: str = "",
) -> str:
    """User message for review LLM — materials only, no echoed user question."""
    return build_multi_source_user_prompt(
        "请基于下列【多源材料】撰写结构化综述。",
        context_block,
        prior_excerpt=prior_review_excerpt,
        prior_header=(
            "【上一版综述（修订参考：保留仍有效的论述，按系统指令中的本轮要求调整；"
            "勿整段复制无关部分）】"
        ),
    )
