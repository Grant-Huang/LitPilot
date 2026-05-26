"""LLM planner — streaming think narration + structured router output."""
from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agents.agent_settings import (
    get_think_max_tokens,
    get_think_mode,
    get_think_use_reasoning,
    get_use_llm_planner,
)
from app.agents.literature_router import (
    LiteratureRouterResult,
    _fallback_title,
    _parse_router_json,
    _sanitize_session_title,
    route_literature,
)
from app.core.think_stream import (
    ThinkAccumulator,
    emit_system_think_line,
    stream_llm_to_think,
)
from app.llm.base import LLMMessage
from app.services.llm_service import get_planner_llm

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")

FETCH_NARRATE_EVERY_N = 5
FETCH_NARRATE_INTERVAL_SEC = 8.0

UNDERSTANDING_SYSTEM = """你是文献综述助手的过程解说员与检索路由器。
任务：
1. 用 2–4 句中文（或与用户同语言）说明：研究主题、拟采用的检索思路、应关注的子方向。
   不要编造具体论文标题、作者或 DOI；不要写综述正文。
2. 最后一行单独输出 JSON（不要 markdown 代码块）：
{"session_title":"8-24字会话标题","search_query":"≤120字学术检索查询"}
禁止泛称「新综述」「文献综述」作为 session_title。"""

NARRATE_SEARCH_AFTER = """你是文献综述的过程解说员。根据【检索结果】用 2–4 句话说明：
- 命中规模与整体相关性
- 接下来抓取时的优先级（1–2 条原则）
不要编造未在列表中出现的论文细节。不要输出 JSON。"""

NARRATE_FETCH_AFTER = """你是文献综述的过程解说员。根据【抓取结果】用 2–4 句话说明：
- 成功/失败概况
- 对后续引用抽取与综述撰写的含义
不要编造数字；以【抓取结果】为准。不要输出 JSON。"""

NARRATE_SEARCH_BEFORE = """你是文献综述的过程解说员。根据【即将执行的检索】用 2–3 句话说明：
- 将采用何种检索策略、为何这样查
- 对用户上传链接与 Tavily 结果如何取舍（若有）
不要编造文献。不要输出 JSON。"""

NARRATE_FETCH_PROGRESS = """你是文献综述的过程解说员。根据【抓取进度】用 1–3 句话简要更新：
- 当前完成比例与成功/失败趋势
- 若某类站点频繁失败，一句话提示
不要编造数字。不要输出 JSON。"""

NARRATE_CITE_AFTER = """你是文献综述的过程解说员。根据【引用抽取结果】用 2–3 句话说明：
- 可核实引用条数是否充足
- 对综述参考文献章节的预期
不要编造条目。不要输出 JSON。"""

NARRATE_GENERATE_BEFORE = """你是文献综述的过程解说员。根据【生成前材料概况】用 2–3 句话说明：
- 将采用的综述结构侧重
- 材料覆盖上的主要限制（若有）
不要写综述正文。不要输出 JSON。"""

CHECKPOINT_SYSTEM = {
    "B": NARRATE_SEARCH_BEFORE,
    "C": NARRATE_SEARCH_AFTER,
    "D": NARRATE_FETCH_PROGRESS,
    "E": NARRATE_FETCH_AFTER,
    "F": NARRATE_CITE_AFTER,
    "G": NARRATE_GENERATE_BEFORE,
}


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
    think_mode: str
    use_reasoning: bool
    max_tokens: int


async def load_planner_context() -> PlannerContext:
    return PlannerContext(
        use_llm_planner=await get_use_llm_planner(),
        think_mode=await get_think_mode(),
        use_reasoning=await get_think_use_reasoning(),
        max_tokens=await get_think_max_tokens(),
    )


def should_narrate(checkpoint: str, ctx: PlannerContext) -> bool:
    if not ctx.use_llm_planner or ctx.think_mode == "off":
        return False
    if ctx.think_mode == "lite":
        return checkpoint in ("A", "C", "E")
    return checkpoint in ("A", "B", "C", "D", "E", "F", "G")


def _extract_router_from_text(text: str, user_message: str) -> LiteratureRouterResult:
    msg = user_message.strip()
    fallback_q = msg[:200] if msg else ""
    fallback = LiteratureRouterResult(
        session_title=_fallback_title(msg),
        search_query=fallback_q,
    )
    raw = (text or "").strip()
    if not raw:
        return fallback
    if not _JSON_BLOCK.search(raw):
        return fallback
    try:
        data = _parse_router_json(raw)
    except (ValueError, json.JSONDecodeError):
        return fallback
    title = _sanitize_session_title(str(data.get("session_title") or ""), msg)
    search_query = str(data.get("search_query") or msg).strip()[:200] or fallback_q
    return LiteratureRouterResult(session_title=title, search_query=search_query)


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
                    session_title=_fallback_title(""),
                    search_query="",
                )
            },
        )
        return

    if not ctx.use_llm_planner:
        result = await route_literature(user_message)
        yield ("__router_result__", {"result": result})
        return

    if ctx.think_mode == "off":
        result = await route_literature(user_message)
        yield ("__router_result__", {"result": result})
        return

    content_buf: list[str] = []
    try:
        llm = await get_planner_llm()
        async for ev in stream_llm_to_think(
            llm,
            [LLMMessage(role="user", content=msg[:800])],
            system=UNDERSTANDING_SYSTEM,
            accumulator=think_acc,
            max_tokens=ctx.max_tokens,
            temperature=0.2,
            use_reasoning=ctx.use_reasoning,
            hide_json_in_stream=True,
            content_buffer=content_buf,
        ):
            yield ev
        merged = "".join(content_buf)
        result = _extract_router_from_text(merged, user_message)
    except Exception:
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

    system = CHECKPOINT_SYSTEM.get(checkpoint)
    if not system:
        return

    body = f"【用户问题】\n{user_message.strip()[:500]}\n\n{context_text.strip()[:6000]}"
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
        lines.append(f"【Tavily 摘要】\n{answer.strip()[:800]}")
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
    tavily_max_results: int,
    upload_count: int,
    skipped_tavily: bool,
) -> str:
    lines = [
        f"【检索查询】\n{query}",
        f"【来源策略】{source_mode}",
        f"【Tavily 上限】{tavily_max_results} 条",
        f"【用户上传链接】{upload_count} 条",
    ]
    if skipped_tavily:
        lines.append("【说明】将跳过 Tavily，仅使用用户列表")
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
