"""LLM planner — streaming think narration + structured router output."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agents.agent_settings import (
    get_orchestrator_max_tokens,
    get_orchestrator_mode,
    get_orchestrator_use_reasoning,
    get_use_llm_planner,
)
from app.agents.prompt_registry import (
    DEFAULT_NARRATE_ATTRIBUTES_AFTER as NARRATE_ATTRIBUTES_AFTER,
    DEFAULT_NARRATE_CITE_AFTER as NARRATE_CITE_AFTER,
    DEFAULT_NARRATE_FETCH_AFTER as NARRATE_FETCH_AFTER,
    DEFAULT_NARRATE_FETCH_PROGRESS as NARRATE_FETCH_PROGRESS,
    DEFAULT_NARRATE_GENERATE_BEFORE as NARRATE_GENERATE_BEFORE,
    DEFAULT_NARRATE_SEARCH_AFTER as NARRATE_SEARCH_AFTER,
    DEFAULT_NARRATE_SEARCH_BEFORE as NARRATE_SEARCH_BEFORE,
    DEFAULT_UNDERSTANDING_SYSTEM as UNDERSTANDING_SYSTEM,

)
from app.agents.prompt_settings import (
    get_narrate_checkpoint_system_prompt,
    get_understanding_system_prompt,
)
from app.agents.literature_router import (
    LiteratureRouterResult,
    build_router_result,
    fallback_router_result,
    fallback_session_title,
    parse_router_json,
    refine_router_session_title,
    route_literature,
    sanitize_session_title,
)
from app.core.think_stream import (
    ThinkAccumulator,
    emit_system_think_line,
    stream_llm_to_think,
)
from app.llm.base import LLMMessage
from app.services.llm_service import get_planner_llm

_log = logging.getLogger(__name__)

FETCH_NARRATE_EVERY_N = 5
FETCH_NARRATE_INTERVAL_SEC = 8.0
# Checkpoint A merges narration + router JSON; needs more budget than later checkpoints.
UNDERSTANDING_MIN_TOKENS = 420

@dataclass
class FetchNarrationThrottle:
    """full 模式检查点 D：每 N 篇完成或间隔 T 秒触发一次解说。"""

    every_n: int = FETCH_NARRATE_EVERY_N
    interval_sec: float = FETCH_NARRATE_INTERVAL_SEC
    _since_narrate: int = field(default=0, init=False)
    _last_narrate: float = field(default_factory=time.monotonic, init=False)

    def should_narrate(self) -> bool:
        if self._since_narrate >= self.every_n:
            return True
        return (time.monotonic() - self._last_narrate) >= self.interval_sec

    def note_completed(self) -> bool:
        self._since_narrate += 1
        return self.should_narrate()

    def mark_narrated(self) -> None:
        self._since_narrate = 0
        self._last_narrate = time.monotonic()


@dataclass
class PlannerContext:
    use_llm_planner: bool
    orchestrator_mode: str
    use_reasoning: bool
    max_tokens: int
    narration_focus: str = ""
    writing_emphasis: str = ""


async def load_planner_context() -> PlannerContext:
    return PlannerContext(
        use_llm_planner=await get_use_llm_planner(),
        orchestrator_mode=await get_orchestrator_mode(),
        use_reasoning=await get_orchestrator_use_reasoning(),
        max_tokens=await get_orchestrator_max_tokens(),
    )


def should_narrate(checkpoint: str, ctx: PlannerContext) -> bool:
    if not ctx.use_llm_planner or ctx.orchestrator_mode == "off":
        return False
    if ctx.orchestrator_mode == "lite":
        return checkpoint in ("A", "C", "E", "F2")
    return checkpoint in ("A", "B", "C", "D", "E", "F", "F2", "G")


def _extract_router_from_text(text: str, user_message: str) -> LiteratureRouterResult:
    msg = user_message.strip()
    fallback = fallback_router_result(msg)
    raw = (text or "").strip()
    if not raw:
        return fallback
    try:
        data = parse_router_json(raw)
    except (ValueError, json.JSONDecodeError):
        return fallback
    return build_router_result(data, msg)


async def stream_understanding_and_route(
    user_message: str,
    *,
    think_acc: ThinkAccumulator | None = None,
    ctx: PlannerContext | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Checkpoint A — 流式思考 + 合并 router（单次 LLM 调用）。"""
    if ctx is None:
        ctx = await load_planner_context()
    msg = user_message.strip()
    if not msg:
        yield (
            "__router_result__",
            {
                "result": LiteratureRouterResult(
                    session_title=fallback_session_title(""),
                    search_query="",
                )
            },
        )
        return

    if not ctx.use_llm_planner:
        result = await route_literature(user_message)
        yield ("__router_result__", {"result": result})
        return

    if ctx.orchestrator_mode == "off":
        result = await route_literature(user_message)
        yield ("__router_result__", {"result": result})
        return

    content_buf: list[str] = []
    understand_tokens = max(ctx.max_tokens, UNDERSTANDING_MIN_TOKENS)
    try:
        llm = await get_planner_llm()
        understanding_system = await get_understanding_system_prompt()
        async for ev in stream_llm_to_think(
            llm,
            [LLMMessage(role="user", content=msg[:800])],
            system=understanding_system,
            accumulator=think_acc,
            max_tokens=understand_tokens,
            temperature=0.2,
            use_reasoning=ctx.use_reasoning,
            hide_json_in_stream=True,
            content_buffer=content_buf,
        ):
            yield ev
        merged = "".join(content_buf)
        result = _extract_router_from_text(merged, user_message)
        result = await refine_router_session_title(result, user_message)
    except Exception:
        _log.exception("orchestrator understanding/route failed; fallback to rules")
        result = await route_literature(user_message)
        async for ev in emit_system_think_line(
            "规划模型暂不可用，已使用规则回退生成检索查询。",
            accumulator=think_acc,
        ):
            yield ev

    yield ("__router_result__", {"result": result})


async def narrate_phase_stream(
    checkpoint: str,
    user_message: str,
    context_text: str,
    *,
    think_acc: ThinkAccumulator | None = None,
    ctx: PlannerContext | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    if ctx is None:
        ctx = await load_planner_context()
    if not should_narrate(checkpoint, ctx):
        return

    system = await get_narrate_checkpoint_system_prompt(checkpoint)
    if not system:
        return

    focus_parts: list[str] = []
    if ctx.narration_focus.strip():
        focus_parts.append(
            f"【本轮解说重点（由规划模型生成）】\n{ctx.narration_focus.strip()}"
        )
    if ctx.writing_emphasis.strip() and checkpoint == "G":
        focus_parts.append(f"【写作侧重】\n{ctx.writing_emphasis.strip()}")
    focus_block = ("\n\n".join(focus_parts) + "\n\n") if focus_parts else ""
    body = (
        f"【用户问题】\n{user_message.strip()[:500]}\n\n"
        f"{focus_block}{context_text.strip()[:6000]}"
    )
    try:
        llm = await get_planner_llm()
        async for ev in stream_llm_to_think(
            llm,
            [LLMMessage(role="user", content=body)],
            system=system,
            accumulator=think_acc,
            max_tokens=ctx.max_tokens,
            temperature=0.25,
            use_reasoning=ctx.use_reasoning,
        ):
            yield ev
    except Exception:
        _log.exception("orchestrator phase narration failed; skip narration")
        async for ev in emit_system_think_line(
            "本阶段解说暂不可用，请查看下方工具结果。",
            accumulator=think_acc,
        ):
            yield ev


def format_search_context(
    hits: list[dict[str, str]],
    answer: str,
    *,
    query: str,
) -> str:
    lines = [f"【检索查询】\n{query}", f"【命中数】{len(hits)}"]
    if answer.strip():
        lines.append(f"【检索摘要】\n{answer.strip()[:800]}")
    if hits:
        lines.append("【标题列表（前 8 条）】")
        for i, h in enumerate(hits[:8], 1):
            title = (h.get("title") or "").strip() or h.get("url", "")
            lines.append(f"{i}. {title}")
    return "\n".join(lines)


def format_fetch_context(
    *,
    total: int,
    ok: int,
    failed: int,
    failed_hosts: list[str],
) -> str:
    lines = [
        f"【计划抓取】{total} 篇",
        f"【成功】{ok} 篇",
        f"【失败】{failed} 篇",
    ]
    if failed_hosts:
        lines.append("【失败域名】" + ", ".join(failed_hosts[:6]))
    return "\n".join(lines)


def format_search_before_context(
    *,
    query: str,
    source_mode: str,
    search_max_results: int,
    upload_count: int,
    skipped_web_search: bool,
    search_provider: str = "native",
) -> str:
    from app.agents.tools.web_providers import search_provider_display

    provider_label = search_provider_display(search_provider)
    lines = [
        f"【检索查询】\n{query}",
        f"【来源策略】{source_mode}",
        f"【检索后端】{provider_label}",
        f"【检索上限】{search_max_results} 条",
        f"【用户上传链接】{upload_count} 条",
    ]
    if skipped_web_search:
        lines.append("【说明】将跳过 web_search，仅使用用户列表")
    return "\n".join(lines)


def format_fetch_progress_context(
    *,
    total: int,
    completed: int,
    ok: int,
    failed: int,
    recent_labels: list[str],
) -> str:
    lines = [
        f"【计划】{total} 篇",
        f"【已完成】{completed}/{total}",
        f"【成功】{ok} 篇",
        f"【失败】{failed} 篇",
    ]
    if recent_labels:
        lines.append("【最近完成】" + "; ".join(recent_labels[:5]))
    return "\n".join(lines)


def format_cite_context(
    cite_records: list[Any],
    *,
    fmt_label: str,
) -> str:
    ok_n = sum(1 for r in cite_records if getattr(r, "success", False))
    fail_n = len(cite_records) - ok_n
    lines = [
        f"【引用格式】{fmt_label}",
        f"【成功抽取】{ok_n} 条",
        f"【失败/不完整】{fail_n} 条",
    ]
    samples: list[str] = []
    for r in cite_records:
        if not getattr(r, "success", False):
            continue
        title = str(getattr(r, "title", "") or "").strip()
        if title:
            samples.append(title[:80])
        if len(samples) >= 5:
            break
    if samples:
        lines.append("【样例标题】" + " | ".join(samples))
    return "\n".join(lines)


def format_generate_context(
    *,
    source_blocks: int,
    cite_ok: int,
    failed_fetch: int,
    fmt_label: str,
) -> str:
    return "\n".join(
        [
            f"【材料分栏数】{source_blocks}",
            f"【可引用条目】约 {cite_ok} 条（{fmt_label}）",
            f"【抓取失败】{failed_fetch} 篇（可能仅用摘要）",
        ]
    )
