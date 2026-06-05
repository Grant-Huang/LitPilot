"""Multi-turn literature session intent routing (P0–P2)."""
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
from app.agents.prompt_settings import get_intent_router_system_prompt
from app.agents.literature_router import (
    LiteratureRouterResult,
    clamp_search_query,
    fallback_session_title,
    parse_router_json,
    route_literature,
    sanitize_session_title,
)
from app.agents.session_corpus import (
    SessionCorpus,
    collect_failed_urls,
    filter_new_urls,
    list_session_library_items,
)
from app.agents.url_list import parse_urls_from_text, sanitize_fetch_urls
from app.library.dedupe import dedupe_library
from app.library.store import LibraryStore
from app.llm.base import LLMMessage
from app.services.llm_service import get_planner_llm

IntentKind = Literal[
    "new_topic",
    "supplement",
    "refine_gen",
    "regen_only",
    "expand_search",
    "retry_failed",
    "query_corpus",
    "manage_library",
    "synthesis_matrix",
]

VALID_INTENTS: frozenset[str] = frozenset(
    {
        "new_topic",
        "supplement",
        "refine_gen",
        "regen_only",
        "expand_search",
        "retry_failed",
        "query_corpus",
        "manage_library",
        "synthesis_matrix",
    }
)

_RETRY_RE = re.compile(r"重试|再试|retry|失败的链接|失败项", re.I)
_REFINE_RE = re.compile(
    r"重点|增加.{0,6}节|改成|只要|不要写|侧重|缩短|英文|表格|篇幅|语气|结构",
    re.I,
)
_REGEN_RE = re.compile(r"重新写|再写一遍|重写|换个角度|再来一版", re.I)
_EXPAND_RE = re.compile(r"再搜|补充检索|找更多|扩展检索|继续检索|更多文献", re.I)
_QUERY_RE = re.compile(
    r"[?？]$|是什么|哪篇|对比|列出|总结这篇|核心结论|谁用了|有没有",
    re.I,
)
_MANAGE_RE = re.compile(r"删除|去掉|移除|导出|去重|合并重复|不参与|排除", re.I)
_DEFER_GEN_RE = re.compile(r"先不写|暂不生成|不要生成|只抓取|仅抓取|先补充", re.I)
_MATRIX_RE = re.compile(
    r"文献综述矩阵|综述矩阵|综合矩阵|synthesis\s+matrix|matrix",
    re.I,
)
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

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
    session_title: str = ""
    search_query: str = ""
    gen_directives: str = ""
    defer_generate: bool = False
    skip_web_search: bool = False
    skip_fetch: bool = False
    use_existing_corpus: bool = False
    manage_action: str = ""
    manage_targets: list[str] = field(default_factory=list)
    new_urls: list[str] = field(default_factory=list)

    def to_router_result(self) -> LiteratureRouterResult:
        return LiteratureRouterResult(
            session_title=self.session_title,
            search_query=self.search_query,
        )


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


def detect_intent_rules(
    user_message: str,
    *,
    turn_ctx: SessionTurnContext,
    extra_urls: list[str] | None = None,
    corpus: SessionCorpus | None = None,
    last_failed: list[dict[str, str]] | None = None,
) -> LiteratureIntentResult | None:
    msg = user_message.strip()
    if not msg and not extra_urls:
        return None

    urls = _extract_urls(msg, extra_urls)
    defer = bool(_DEFER_GEN_RE.search(msg))

    if _MATRIX_RE.search(msg):
        return LiteratureIntentResult(
            intent="synthesis_matrix",
            search_query=msg[:200],
            gen_directives=msg[:500],
            new_urls=urls,
            defer_generate=False,
            skip_web_search=turn_ctx.has_corpus and not urls,
            skip_fetch=turn_ctx.has_corpus and not urls,
            use_existing_corpus=turn_ctx.has_corpus,
        )

    if not turn_ctx.has_corpus and turn_ctx.user_turns <= 1:
        return LiteratureIntentResult(
            intent="new_topic",
            search_query=msg[:200],
            session_title=fallback_session_title(msg),
            new_urls=urls,
            use_existing_corpus=False,
        )

    if urls:
        new_only = filter_new_urls(corpus, urls)
        return LiteratureIntentResult(
            intent="supplement",
            search_query=msg[:200],
            session_title="",
            new_urls=new_only or urls,
            defer_generate=defer,
            skip_web_search=True,
            use_existing_corpus=True,
        )

    if turn_ctx.failed_count and _RETRY_RE.search(msg):
        retry_urls = collect_failed_urls(corpus, last_failed)
        return LiteratureIntentResult(
            intent="retry_failed",
            new_urls=retry_urls,
            defer_generate=defer,
            skip_web_search=True,
            use_existing_corpus=True,
        )

    if _MANAGE_RE.search(msg):
        action, targets = parse_manage_command(msg, turn_ctx.session_id)
        return LiteratureIntentResult(
            intent="manage_library",
            manage_action=action,
            manage_targets=targets,
            defer_generate=True,
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    if turn_ctx.has_corpus and _QUERY_RE.search(msg) and len(msg) < 400:
        if not _REFINE_RE.search(msg) and not _REGEN_RE.search(msg):
            return LiteratureIntentResult(
                intent="query_corpus",
                defer_generate=True,
                skip_web_search=True,
                skip_fetch=True,
                use_existing_corpus=True,
            )

    if _REFINE_RE.search(msg):
        return LiteratureIntentResult(
            intent="refine_gen",
            gen_directives=msg[:500],
            defer_generate=defer,
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    if _REGEN_RE.search(msg):
        return LiteratureIntentResult(
            intent="regen_only",
            defer_generate=defer,
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    if _EXPAND_RE.search(msg):
        return LiteratureIntentResult(
            intent="expand_search",
            search_query=msg[:200],
            defer_generate=defer,
            use_existing_corpus=True,
        )

    if turn_ctx.has_corpus and turn_ctx.has_review and len(msg) < 120:
        return LiteratureIntentResult(
            intent="refine_gen",
            gen_directives=msg[:500],
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    return None


def _parse_intent_json(raw: str, user_message: str) -> LiteratureIntentResult:
    msg = user_message.strip()
    fallback = LiteratureIntentResult(
        intent="refine_gen" if msg else "new_topic",
        search_query=clamp_search_query(msg, fallback=msg),
        session_title=fallback_session_title(msg),
        gen_directives=msg[:500],
        use_existing_corpus=bool(msg),
    )
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        data = parse_router_json(text)
    except (ValueError, json.JSONDecodeError):
        return fallback

    intent = str(data.get("intent") or "refine_gen").strip()
    if intent not in VALID_INTENTS:
        intent = "refine_gen"

    return LiteratureIntentResult(
        intent=intent,  # type: ignore[arg-type]
        session_title=sanitize_session_title(
            str(data.get("session_title") or ""),
            msg,
        ),
        search_query=clamp_search_query(
            str(data.get("search_query") or msg),
            fallback=clamp_search_query(msg, fallback=msg),
        ),
        gen_directives=str(data.get("gen_directives") or msg).strip()[:500],
        defer_generate=bool(data.get("defer_generate")),
        skip_web_search=bool(data.get("skip_web_search")),
        skip_fetch=bool(data.get("skip_fetch")),
        use_existing_corpus=bool(data.get("use_existing_corpus", True)),
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
    if ruled and ruled.intent != "refine_gen":
        if ruled.intent == "new_topic" or not turn_ctx.has_corpus:
            return ruled
        if ruled.intent in (
            "supplement",
            "retry_failed",
            "manage_library",
            "query_corpus",
            "regen_only",
            "expand_search",
            "synthesis_matrix",
        ):
            return ruled

    if not turn_ctx.has_corpus:
        router = await route_literature(user_message)
        urls = _extract_urls(user_message, extra_urls)
        return LiteratureIntentResult(
            intent="new_topic",
            session_title=router.session_title,
            search_query=router.search_query,
            new_urls=urls,
            use_existing_corpus=False,
        )

    try:
        llm = await get_planner_llm()
        body = (
            f"【会话状态】\n{format_session_context_summary(turn_ctx)}\n\n"
            f"【用户消息】\n{user_message.strip()[:800]}"
        )
        if extra_urls:
            body += f"\n\n【上传链接数】{len(extra_urls)}"
        intent_system = await get_intent_router_system_prompt()
        resp = await llm.chat(
            [LLMMessage(role="user", content=body)],
            system=intent_system,
            max_tokens=300,
            temperature=0.0,
        )
        result = _parse_intent_json(resp.content or "", user_message)
    except Exception:
        result = LiteratureIntentResult(
            intent="refine_gen",
            gen_directives=user_message.strip()[:500],
            skip_web_search=True,
            skip_fetch=True,
            use_existing_corpus=True,
        )

    urls = _extract_urls(user_message, extra_urls)
    if urls:
        result.intent = "supplement"
        result.new_urls = filter_new_urls(corpus, urls) or urls
        result.skip_web_search = True
        result.use_existing_corpus = True

    if result.intent == "new_topic" and turn_ctx.has_corpus:
        result.intent = "expand_search"
        if not result.search_query:
            result.search_query = user_message.strip()[:200]

    if result.intent == "expand_search" and not result.search_query:
        result.search_query = user_message.strip()[:200]

    if result.intent == "synthesis_matrix":
        if not result.search_query:
            result.search_query = user_message.strip()[:200]
        if turn_ctx.has_corpus and not urls:
            result.skip_web_search = True
            result.skip_fetch = True
            result.use_existing_corpus = True
        elif not turn_ctx.has_corpus:
            result.use_existing_corpus = False

    if result.intent in ("refine_gen", "regen_only") and not result.gen_directives:
        if result.intent == "refine_gen":
            result.gen_directives = user_message.strip()[:500]

    if result.intent == "retry_failed":
        result.new_urls = collect_failed_urls(corpus, last_failed)

    return result


def parse_manage_command(
    user_message: str,
    session_id: str,
) -> tuple[str, list[str]]:
    msg = user_message.strip()
    if re.search(r"导出|参考文献列表|ref.?list", msg, re.I):
        return "export_refs", []

    if re.search(r"去重|合并重复", msg, re.I):
        return "dedupe", []

    items = list_session_library_items(session_id)
    targets: list[str] = []

    idx_match = re.search(r"第\s*(\d+)\s*[篇条]", msg)
    if idx_match:
        idx = int(idx_match.group(1))
        for item in items:
            if int(item.get("display_index") or 0) == idx:
                targets.append(str(item.get("id") or ""))
                break
        return "remove", [t for t in targets if t]

    url_match = parse_urls_from_text(msg)
    if url_match:
        return "remove", url_match

    title_match = re.search(r"(?:删除|去掉|移除|排除)\s*[「\"']?(.+?)[」\"']?\s*$", msg)
    if title_match:
        needle = title_match.group(1).strip().lower()
        for item in items:
            title = str(item.get("title") or "").lower()
            if needle and needle in title:
                targets.append(str(item.get("id") or ""))
        return "remove", [t for t in targets if t]

    return "list", []


def execute_manage_library(
    action: str,
    targets: list[str],
    session_id: str,
) -> str:
    lib = LibraryStore()
    items = list_session_library_items(session_id)

    if action == "export_refs":
        lines = []
        for item in items:
            apa = (item.get("citations") or {}).get("apa") or ""
            if apa:
                lines.append(apa)
            elif item.get("url"):
                lines.append(f"- {item.get('title') or item['url']} {item['url']}")
        if not lines:
            return "当前会话文献库中没有可导出的引用条目。"
        return "## 会话参考文献\n\n" + "\n\n".join(lines)

    if action == "dedupe":
        before = len(lib.list_items())
        dedupe_library(lib)
        after = len(lib.list_items())
        return f"已对全局文献库去重：{before} → {after} 条。"

    if action == "remove":
        removed = 0
        id_set = set(targets)
        for item in items:
            iid = str(item.get("id") or "")
            url = str(item.get("url") or "")
            if iid in id_set or url in id_set:
                if lib.delete_item(iid):
                    removed += 1
        if removed:
            return f"已从文献库移除 {removed} 条与会话相关的文献。如需更新综述，请说明新的写作要求。"
        return "未找到要删除的文献。请指定序号（如「删除第 3 篇」）或 URL。"

    if action == "list":
        if not items:
            return "当前会话尚无文献库条目。"
        lines = ["当前会话文献库："]
        for item in items[:20]:
            idx = item.get("display_index")
            title = item.get("title") or item.get("url")
            lines.append(f"- [{idx}] {title}")
        return "\n".join(lines)

    return "未能识别文献库管理指令。支持：删除第 N 篇、导出参考文献、去重。"


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
    """Deprecated: use build_review_materials_user_prompt for LLM user message."""
    del initial_query, user_message, intent, gen_constraints
    block = (context_block or "").strip()
    return f"请基于下列多源材料撰写结构化综述。\n\n【多源材料】\n{block}"


def build_query_prompt(
    *,
    initial_query: str,
    user_message: str,
    context_block: str,
) -> str:
    parts = []
    if initial_query:
        parts.append(f"研究背景：{initial_query[:300]}")
    parts.append(f"用户问题：{user_message.strip()}")
    parts.append(f"{MULTI_SOURCE_MATERIALS_HEADER}\n{context_block[:60_000]}")
    return "\n\n".join(parts)
