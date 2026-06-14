"""Multi-turn literature session intent routing (v2)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.prompt_registry import (
    DEFAULT_INTENT_ROUTER_SYSTEM as INTENT_ROUTER_SYSTEM,
    DEFAULT_QUERY_CORPUS_SYSTEM as QUERY_CORPUS_SYSTEM,
)
from app.agents.review_prompt import MULTI_SOURCE_MATERIALS_HEADER
from app.agents.prompt_settings import get_intent_router_system_prompt, get_prompt_max_tokens
from app.agents.literature_router import (
    parse_router_json,
)
from app.agents.session_corpus import (
    SessionCorpus,
    filter_new_urls,
    list_session_library_items,
)
from app.agents.url_list import parse_urls_from_text, sanitize_fetch_urls
from app.llm.base import LLMMessage
from app.services.llm_service import get_router_llm

IntentKind = Literal[
    "new_topic",
    "subtopic_change",
    "append_urls",
    "review_refine",
    "query_corpus",
    "short_answer",
]

VALID_INTENTS: frozenset[str] = frozenset(
    {
        "new_topic",
        "subtopic_change",
        "append_urls",
        "review_refine",
        "query_corpus",
        "short_answer",
    }
)

_SUBTOPIC_ADD_RE = re.compile(
    r"增加子主题|加一个子主题|新增子主题|添加子主题",
    re.I,
)
_SUBTOPIC_MODIFY_RE = re.compile(
    r"修改子主题|更新子主题|把子主题|改子主题",
    re.I,
)
_REVIEW_REFINE_RE = re.compile(
    r"重点|增加.{0,6}节|改成|只要|不要写|侧重|缩短|英文|表格|篇幅|语气|结构|"
    r"只改|只重写|修订|更新第.{0,4}章|重写第|改写第",
    re.I,
)
_FULL_REGEN_RE = re.compile(r"整篇重写|全文重新生成|全部重写|重新写一遍|再来一版", re.I)
_QUERY_RE = re.compile(
    r"[?？]$|是什么|哪篇|对比|列出|总结这篇|核心结论|谁用了|有没有",
    re.I,
)
_EXPAND_HINT_RE = re.compile(r"再搜|补充检索|找更多|扩展检索|继续检索|更多文献", re.I)
_EXPLICIT_WRITE_RE = re.compile(
    r"(帮我|请|直接|现在|开始)?(撰写|写|生成)(综述|文献综述|总结报告|综合报告)"
    r"|帮我写|开始(撰写|写|生成)|直接(撰写|写|生成)",
    re.I,
)
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

CORPUS_GUIDANCE_FOOTER = (
    "\n\n——\n"
    "若要**增加或修改子主题**，请明确说明，例如：「增加子主题：零信任架构」或「修改子主题 2：…」。"
    "如需**追加文献链接**，请使用输入框「+」上传或粘贴 URL。"
    "如需**只改综述表述**，请说明章节与修改要求。"
)


@dataclass
class SessionTurnContext:
    session_id: str
    user_turns: int
    has_corpus: bool
    corpus_source_blocks: int
    has_review: bool
    initial_query: str
    gen_constraints: list[str]
    failed_count: int
    library_item_count: int


@dataclass
class LiteratureIntentResult:
    intent: IntentKind
    gen_directives: str = ""
    defer_generate: bool = False
    skip_web_search: bool = False
    skip_fetch: bool = False
    use_existing_corpus: bool = False
    new_urls: list[str] = field(default_factory=list)
    subtopic_op: str = ""
    full_regen: bool = False
    append_guidance_hint: str = ""


def normalize_intent(raw: str) -> IntentKind:
    intent = (raw or "").strip()
    if intent in VALID_INTENTS:
        return intent  # type: ignore[arg-type]
    _legacy: dict[str, IntentKind] = {
        "supplement": "append_urls",
        "refine_gen": "review_refine",
        "regen_only": "review_refine",
    }
    return _legacy.get(intent, "short_answer")


def build_session_turn_context(
    *,
    session_id: str,
    session_meta: dict[str, Any],
    user_turns: int,
    corpus: SessionCorpus | None,
    last_failed: list[dict[str, str]] | None,
    has_review: bool,
) -> SessionTurnContext:
    failed = last_failed or (corpus.failed_literature if corpus else [])
    return SessionTurnContext(
        session_id=session_id,
        user_turns=user_turns,
        has_corpus=bool(corpus and (corpus.fetch_hits or corpus.sources_md)),
        corpus_source_blocks=corpus.source_block_count() if corpus else 0,
        has_review=has_review,
        initial_query=str(session_meta.get("initial_query") or ""),
        gen_constraints=list(session_meta.get("gen_constraints") or []),
        failed_count=len(failed),
        library_item_count=len(list_session_library_items(session_id)),
    )


def format_session_context_summary(ctx: SessionTurnContext) -> str:
    lines = [
        f"用户轮次: {ctx.user_turns}",
        f"已有语料: {'是' if ctx.has_corpus else '否'}（{ctx.corpus_source_blocks} 个材料块）",
        f"已有综述: {'是' if ctx.has_review else '否'}",
        f"首轮问题: {ctx.initial_query[:200] or '（未记录）'}",
        f"累积写作约束: {len(ctx.gen_constraints)} 条",
        f"失败文献: {ctx.failed_count} 条",
        f"会话文献库条目: {ctx.library_item_count}",
    ]
    if ctx.gen_constraints:
        lines.append("约束摘要: " + "; ".join(c[:60] for c in ctx.gen_constraints[-3:]))
    return "\n".join(lines)


def _extract_urls(user_message: str, extra_urls: list[str] | None) -> list[str]:
    from_msg = parse_urls_from_text(user_message)
    merged = sanitize_fetch_urls((extra_urls or []) + from_msg)
    return merged


def _query_corpus_result(*, gen_directives: str = "") -> LiteratureIntentResult:
    return LiteratureIntentResult(
        intent="query_corpus",
        gen_directives=gen_directives[:500],
        defer_generate=True,
        skip_web_search=True,
        skip_fetch=True,
        use_existing_corpus=True,
    )


def _short_answer_result(*, gen_directives: str = "") -> LiteratureIntentResult:
    return LiteratureIntentResult(
        intent="short_answer",
        gen_directives=gen_directives[:500],
        defer_generate=True,
        skip_web_search=True,
        skip_fetch=True,
        use_existing_corpus=True,
    )


def detect_intent_rules(
    user_message: str,
    *,
    turn_ctx: SessionTurnContext,
    extra_urls: list[str] | None = None,
    corpus: SessionCorpus | None = None,
    last_failed: list[dict[str, str]] | None = None,
) -> LiteratureIntentResult | None:
    del last_failed
    msg = user_message.strip()
    if not msg and not extra_urls:
        return None

    urls = _extract_urls(msg, extra_urls)
    is_first_turn = not turn_ctx.has_corpus and turn_ctx.user_turns <= 1

    if is_first_turn:
        return LiteratureIntentResult(
            intent="new_topic",
            new_urls=[],
            use_existing_corpus=False,
            skip_web_search=False,
            skip_fetch=False,
        )

    if urls:
        new_only = filter_new_urls(corpus, urls)
        return LiteratureIntentResult(
            intent="append_urls",
            new_urls=new_only or urls,
            defer_generate=True,
            skip_web_search=True,
            use_existing_corpus=True,
        )

    if _SUBTOPIC_ADD_RE.search(msg):
        return LiteratureIntentResult(
            intent="subtopic_change",
            subtopic_op="add",
            gen_directives=msg[:500],
            full_regen=bool(_FULL_REGEN_RE.search(msg)),
            use_existing_corpus=True,
        )

    if _SUBTOPIC_MODIFY_RE.search(msg):
        return LiteratureIntentResult(
            intent="subtopic_change",
            subtopic_op="modify",
            gen_directives=msg[:500],
            full_regen=bool(_FULL_REGEN_RE.search(msg)),
            use_existing_corpus=True,
        )

    if _REVIEW_REFINE_RE.search(msg) or _FULL_REGEN_RE.search(msg):
        return LiteratureIntentResult(
            intent="review_refine",
            gen_directives=msg[:500],
            full_regen=bool(_FULL_REGEN_RE.search(msg)),
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    if _EXPLICIT_WRITE_RE.search(msg) and turn_ctx.has_corpus:
        return LiteratureIntentResult(
            intent="review_refine",
            gen_directives=msg[:500],
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    if turn_ctx.has_corpus and _QUERY_RE.search(msg) and len(msg) < 400:
        return _query_corpus_result()

    return None


def _parse_intent_json(raw: str, user_message: str) -> LiteratureIntentResult:
    msg = user_message.strip()
    fallback = _short_answer_result(gen_directives=msg[:500])
    if not msg:
        fallback = LiteratureIntentResult(
            intent="new_topic",
            use_existing_corpus=False,
        )
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        data = parse_router_json(text)
    except (ValueError, json.JSONDecodeError):
        return fallback

    intent = normalize_intent(str(data.get("intent") or "query_corpus"))
    full_regen = bool(data.get("full_regen")) or intent == "review_refine" and bool(
        _FULL_REGEN_RE.search(msg)
    )

    defer = bool(data.get("defer_generate"))
    # new_topic / subtopic_change 的核心需求就是生成综述，LLM 无权决定是否 defer。
    # 历史表明 LLM 有时在非首轮会话中错误输出 defer_generate: true，
    # 导致搜索+抓取正常完成后跳过生成阶段（用户看到"检索 1 轮 · 抓取 3 篇"后直接结束）。
    if intent in ("new_topic", "subtopic_change"):
        defer = False

    return LiteratureIntentResult(
        intent=intent,
        gen_directives=str(data.get("gen_directives") or msg).strip()[:500],
        defer_generate=defer,
        skip_web_search=bool(data.get("skip_web_search")),
        skip_fetch=bool(data.get("skip_fetch")),
        use_existing_corpus=bool(data.get("use_existing_corpus", True)),
        subtopic_op=str(data.get("subtopic_op") or ""),
        full_regen=full_regen,
    )


async def route_literature_intent(
    user_message: str,
    *,
    turn_ctx: SessionTurnContext,
    extra_urls: list[str] | None = None,
    corpus: SessionCorpus | None = None,
    last_failed: list[dict[str, str]] | None = None,
) -> LiteratureIntentResult:
    ruled = detect_intent_rules(
        user_message,
        turn_ctx=turn_ctx,
        extra_urls=extra_urls,
        corpus=corpus,
        last_failed=last_failed,
    )
    if ruled is not None:
        if ruled.intent == "new_topic":
            ruled.new_urls = []
        return ruled

    if not turn_ctx.has_corpus:
        return LiteratureIntentResult(
            intent="new_topic",
            new_urls=[],
            use_existing_corpus=False,
        )

    try:
        llm = await get_router_llm()
        body = (
            f"【会话状态】\n{format_session_context_summary(turn_ctx)}\n\n"
            f"【用户消息】\n{user_message.strip()[:800]}"
        )
        intent_system = await get_intent_router_system_prompt()
        max_tokens = await get_prompt_max_tokens("intent_router_system_template")
        resp = await llm.chat(
            [LLMMessage(role="user", content=body)],
            system=intent_system,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        result = _parse_intent_json(resp.content or "", user_message)
    except Exception:
        result = _short_answer_result(gen_directives=user_message.strip()[:500])

    result.intent = normalize_intent(result.intent)
    urls = _extract_urls(user_message, extra_urls)
    if urls:
        result.intent = "append_urls"
        result.new_urls = filter_new_urls(corpus, urls) or urls
        result.skip_web_search = True
        result.defer_generate = True
        result.use_existing_corpus = True

    if result.intent == "new_topic" and turn_ctx.has_corpus:
        result.intent = "query_corpus"
        result.defer_generate = True
        result.skip_web_search = True
        result.skip_fetch = True

    if result.intent == "review_refine" and not result.gen_directives:
        result.gen_directives = user_message.strip()[:500]

    return result


def merge_gen_constraints(
    existing: list[str],
    new_directive: str,
) -> list[str]:
    directive = (new_directive or "").strip()
    if not directive:
        return list(existing)
    out = list(existing)
    if directive not in out:
        out.append(directive[:500])
    return out[-10:]


def build_generation_prompt(
    *,
    initial_query: str,
    user_message: str,
    intent: LiteratureIntentResult,
    gen_constraints: list[str],
    context_block: str,
) -> str:
    del initial_query, user_message, intent, gen_constraints
    block = (context_block or "").strip()
    return f"请基于下列多源材料撰写结构化综述。\n\n【多源材料】\n{block}"


def build_query_prompt(
    *,
    initial_query: str,
    user_message: str,
    context_block: str,
    include_guidance: bool = True,
) -> str:
    parts = []
    if initial_query:
        parts.append(f"研究背景：{initial_query[:300]}")
    parts.append(f"用户问题：{user_message.strip()}")
    parts.append(f"{MULTI_SOURCE_MATERIALS_HEADER}\n{context_block[:60_000]}")
    text = "\n\n".join(parts)
    if include_guidance:
        text += CORPUS_GUIDANCE_FOOTER
    return text


def build_append_urls_notice(
    *,
    updated_titles: list[str],
    chapter_hints: list[str] | None = None,
) -> str:
    lines = ["已更新文献库与语料："]
    if updated_titles:
        for i, title in enumerate(updated_titles[:20], 1):
            lines.append(f"{i}. {title}")
    else:
        lines.append("（无新条目；链接可能已在库中）")

    if chapter_hints:
        hint = "、".join(chapter_hints[:5])
        lines.append(f"\n可根据新文献更新：{hint}。")
    else:
        lines.append("\n可根据新文献更新对应章节，例如：「根据新文献更新第二章」。")
    lines.append(
        "如需调整子主题或扩展检索，请明确说明「增加子主题：…」或「修改子主题：…」。"
    )
    return "\n".join(lines)


# Deprecated v1 helpers — kept for import stability during migration.
def parse_manage_command(user_message: str, session_id: str) -> tuple[str, list[str]]:
    del user_message, session_id
    return "list", []


def execute_manage_library(action: str, targets: list[str], session_id: str) -> str:
    del action, targets, session_id
    return (
        "文献库管理请在「文献库」页面操作（删除、去重、重新抓取）。"
        + CORPUS_GUIDANCE_FOOTER
    )
