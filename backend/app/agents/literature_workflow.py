"""Literature review DAG: tavily → jina → cite_extract → LLM → deliver."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from app.agents.agent_settings import (
    get_citation_format,
    get_fetch_parallel,
    get_fetch_retry_count,
    get_fetch_retry_delay_ms,
    get_fetch_timeout_sec,
    get_jina_api_key,
    get_literature_source_mode,
    get_max_fetch_urls,
    get_tavily_api_key,
    get_tavily_max_results,
    get_tavily_retry_count,
)
from app.agents.literature_source import build_fetch_hits, should_skip_tavily
from app.agents.tavily_key import tavily_key_hint
from app.agents.retry_utils import retry_async
from app.agents.agent_skills import skill_active_event
from app.agents.literature_planner import (
    FetchNarrationThrottle,
    format_cite_context,
    format_fetch_context,
    format_fetch_progress_context,
    format_generate_context,
    format_search_before_context,
    format_search_context,
    load_planner_context,
    narrate_phase_stream,
    should_narrate,
    stream_understanding_and_route,
)
from app.agents.literature_router import should_auto_rename_session
from app.core.think_stream import emit_system_think_line
from app.agents.url_list import effective_fetch_cap, sanitize_fetch_urls
from app.agents.parallel_fetch import iter_fetch_sources_parallel
from app.agents.report_compliance import append_compliance_footer
from app.agents.tools.cached_tools import cached_tavily_search
from app.agents.tools.tavily_search import normalize_tavily_results
from app.agents.execution_trace import (
    append_tool,
    append_workflow,
    new_trace,
    upsert_stage,
)
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.agents.workflow_graph import NodeStatus, WorkflowGraph, build_literature_graph
from app.core.think_stream import ThinkAccumulator
from app.llm.base import LLMMessage
from app.services.llm_service import get_llm
from app.skills.citation_extractor import extract_and_persist_batch
from app.library.from_run import upsert_library_from_run
from app.storage.file_store import get_store

MAX_SOURCE_CHARS = 14_000
WORKFLOW_ARTIFACT_LANG = "workflow-graph"

_CITATION_FORMAT_LABELS = {
    "apa": "APA",
    "acm": "ACM",
}


def _generate_system_prompt(citation_format: str) -> str:
    fmt_label = _CITATION_FORMAT_LABELS.get(citation_format, "APA")
    return f"""你是学术文献综述助手。基于提供的多源材料撰写结构化综述。
材料分栏：[Tavily] 为检索摘要；[网页材料] 为正文摘录；[Citations] 为已抽取的 {fmt_label} 条目。
要求：
- 结构：研究背景 → 主要研究工作对比 → 研究空白与未来方向 → 参考文献（{fmt_label}，仅列 [Citations] 中可核实条目）
- 参考文献须严格遵循 {fmt_label} 格式规范
- 仅引用材料中出现的事实；无法核实的标注「待核实」
- 使用与用户相同的语言（中文或英文）
- 不构成代写或抄袭建议；注明需用户自行核实"""


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _chunk_text(text: str, size: int = 28) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


async def _emit_tool(
    name: str,
    args: dict[str, Any],
    output: str,
    *,
    error: str | None = None,
    duration_ms: int | None = None,
    trace: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    tid = _new_id("tc")
    yield (
        "tool_call",
        {
            "id": tid,
            "name": name,
            "args": args,
            "risk": "safe",
            "provider": "api",
        },
    )
    payload: dict[str, Any] = {
        "tool_call_id": tid,
        "output": output if not error else "",
    }
    if error:
        payload["error"] = error
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if trace is not None:
        append_tool(
            trace,
            tool_id=tid,
            name=name,
            args=args,
            status="error" if error else "done",
            output=output if not error else "",
            error=error,
            duration_ms=duration_ms,
        )
    yield ("tool_result", payload)


async def _emit_workflow_graph(
    graph: WorkflowGraph,
    graph_artifact_id: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    yield (
        "artifact",
        {
            "id": graph_artifact_id,
            "lang": WORKFLOW_ARTIFACT_LANG,
            "delta": graph.to_json(),
            "done": True,
        },
    )


async def _publish_workflow_graph(
    graph: WorkflowGraph,
    graph_artifact_id: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Single full-graph snapshot (Meso artifact deltas are append-only)."""
    async for ev in _emit_workflow_graph(graph, graph_artifact_id):
        yield ev


async def _sync_graph_node(
    emitter: WorkflowNodeEmitter,
    graph: WorkflowGraph,
    graph_artifact_id: str,
    node_id: str,
    status: NodeStatus,
    *,
    parent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    graph.set_node_status(node_id, status)
    if status == "active":
        async for ev in emitter.yield_begin(
            node_id, parent_id=parent_id, metadata=metadata
        ):
            yield ev
    elif status == "done":
        async for ev in emitter.yield_finish(
            node_id, "done", parent_id=parent_id, metadata=metadata
        ):
            yield ev
    elif status == "error":
        async for ev in emitter.yield_finish(
            node_id, "error", parent_id=parent_id, metadata=metadata
        ):
            yield ev


def _augment_query(user_message: str) -> str:
    q = user_message.strip()
    if not any(x in q.lower() for x in ("site:", "arxiv", "dblp")):
        q = f"{q} (academic paper survey site:arxiv.org OR site:dblp.org)"
    return q


async def stream_literature_turn(
    session_id: str,
    user_message: str,
    *,
    extra_fetch_urls: list[str] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    store = get_store()
    store.append_message(session_id, "user", user_message)

    citation_format = await get_citation_format()
    fmt_label = _CITATION_FORMAT_LABELS.get(citation_format, "APA")

    yield skill_active_event("literature-review")

    tavily_key = await get_tavily_api_key()
    if not tavily_key:
        yield ("error", {"message": "请先在设置页或 .env 配置 Tavily API Key"})
        return
    key_hint = tavily_key_hint(tavily_key)
    if key_hint:
        yield ("error", {"message": key_hint})
        return

    tavily_max_results = await get_tavily_max_results()
    max_fetch_urls = await get_max_fetch_urls()
    source_mode = await get_literature_source_mode()
    tavily_retry_count = await get_tavily_retry_count()
    fetch_retry_count = await get_fetch_retry_count()
    fetch_retry_delay_ms = await get_fetch_retry_delay_ms()
    upload_urls = sanitize_fetch_urls(extra_fetch_urls)
    skip_tavily = should_skip_tavily(source_mode, upload_urls)

    graph_artifact_id = _new_id("wf")
    emitter = WorkflowNodeEmitter(graph_artifact_id)
    g = build_literature_graph()
    execution_trace = new_trace()
    think_acc = ThinkAccumulator()
    planner_ctx = await load_planner_context()

    async for ev in _publish_workflow_graph(g, graph_artifact_id):
        yield ev

    yield ("stage", {"name": "理解研究问题", "state": "active"})

    session_meta = store.get_session(session_id) or {}
    msgs = store.load_messages(session_id, limit=50)
    user_turns = sum(1 for m in msgs if m.get("role") == "user")
    router_result = None
    async for ev in stream_understanding_and_route(
        user_message,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        if ev[0] == "__router_result__":
            router_result = ev[1]["result"]
        else:
            yield ev
    if router_result is None:
        from app.agents.literature_router import route_literature

        router_result = await route_literature(user_message)

    if should_auto_rename_session(
        session_meta,
        user_message,
        user_message_count=user_turns,
    ):
        new_title = router_result.session_title
        if new_title:
            store.update_session(session_id, title=new_title)
            yield (
                "session_title",
                {"session_id": session_id, "title": new_title},
            )

    yield ("stage", {"name": "理解研究问题", "state": "done"})
    upsert_stage(execution_trace, "理解研究问题", "done")

    base_query = router_result.search_query.strip() or user_message.strip()
    query = _augment_query(base_query)
    hits: list[dict[str, str]] = []
    answer = ""

    yield ("stage", {"name": "文献检索", "state": "active"})

    if skip_tavily:
        async for ev in emit_system_think_line(
            f"已跳过 Tavily 网络检索（用户列表 {len(upload_urls)} 条）。",
            accumulator=think_acc,
        ):
            yield ev
        yield ("stage", {"name": "文献检索", "state": "done"})
        upsert_stage(execution_trace, "文献检索", "done")
    else:
        retry_note = ""
        search_before_ctx = format_search_before_context(
            query=query,
            source_mode=source_mode,
            tavily_max_results=tavily_max_results,
            upload_count=len(upload_urls),
            skipped_tavily=False,
        )
        async for ev in narrate_phase_stream(
            "B",
            user_message,
            search_before_ctx,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            yield ev
        try:

            async def _tavily_call() -> dict:
                return await cached_tavily_search(
                    tavily_key,
                    query,
                    max_results=tavily_max_results,
                    search_depth="advanced",
                )

            t0 = time.monotonic()
            raw_search = await retry_async(
                _tavily_call,
                max_retries=tavily_retry_count,
                delay_ms=fetch_retry_delay_ms,
            )
            search_ms = int((time.monotonic() - t0) * 1000)
            hits = normalize_tavily_results(raw_search)
            answer = str(raw_search.get("answer") or "").strip()
            retry_note = (
                f"，已重试 {tavily_retry_count} 次" if tavily_retry_count else ""
            )
            async for ev in _emit_tool(
                "web_search",
                {"query": query, "provider": "tavily"},
                json.dumps(
                    {
                        "answer": answer[:500],
                        "hits": len(hits),
                        "retries": tavily_retry_count,
                    },
                    ensure_ascii=False,
                ),
                duration_ms=search_ms,
                trace=execution_trace,
            ):
                yield ev
        except Exception as e:
            if not upload_urls:
                fail_msg = f"Tavily 搜索不可用（{e}）。请检查 API Key；本次会话已终止。"
                yield ("text", {"delta": fail_msg})
                store.append_message(session_id, "assistant", fail_msg)
                return
            async for ev in emit_system_think_line(
                f"Tavily 检索失败，将仅使用用户链接（{len(upload_urls)} 条）。",
                accumulator=think_acc,
            ):
                yield ev
        else:
            if not hits and not answer and not upload_urls:
                fail_msg = "未检索到可用文献结果，本次会话已终止。"
                yield ("text", {"delta": fail_msg})
                store.append_message(session_id, "assistant", fail_msg)
                return

        search_ctx = format_search_context(hits, answer, query=query)
        async for ev in narrate_phase_stream(
            "C",
            user_message,
            search_ctx,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            yield ev
        yield ("stage", {"name": "文献检索", "state": "done"})
        upsert_stage(execution_trace, "文献检索", "done")

    fetch_cap = effective_fetch_cap(max_fetch_urls, upload_urls)
    build_result = build_fetch_hits(
        source_mode, hits, upload_urls, max_urls=fetch_cap
    )
    fetch_hits = build_result.hits
    upload_count = build_result.user_count

    yield (
        "literature_source",
        {
            "mode": build_result.mode,
            "user_count": build_result.user_count,
            "tavily_count": build_result.tavily_count,
            "skipped_tavily": build_result.skipped_tavily,
            "total_fetch": len(fetch_hits),
        },
    )

    if not fetch_hits:
        fail_msg = "没有可抓取的文献链接，本次会话已终止。"
        yield ("text", {"delta": fail_msg})
        store.append_message(session_id, "assistant", fail_msg)
        return

    yield ("stage", {"name": "抓取网页", "state": "active"})
    t_fetch = time.monotonic()
    async for ev in emit_system_think_line(
        f"开始并行抓取 {len(fetch_hits)} 篇来源（上限 {fetch_cap}）。",
        accumulator=think_acc,
    ):
        yield ev
    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "fetch", "active"):
        yield ev

    sources_md: list[str] = []
    failed_literature: list[dict[str, str]] = []
    if answer:
        sources_md.append(f"## [Tavily] 检索摘要\n\n{answer}\n")

    jina_key = await get_jina_api_key()
    parallel = await get_fetch_parallel()
    timeout_sec = await get_fetch_timeout_sec()
    llm = await get_llm()
    fetch_idx = 0
    fetch_ok = 0
    fetch_failed = 0
    failed_hosts: list[str] = []
    fetch_results: list[tuple[dict[str, str], str, str | None]] = []
    fetch_throttle = (
        FetchNarrationThrottle()
        if should_narrate("D", planner_ctx)
        else None
    )
    recent_fetch_labels: list[str] = []
    async for hit, ctx_md, err in iter_fetch_sources_parallel(
        fetch_hits,
        api_key=jina_key or None,
        llm=llm,
        parallel=parallel,
        timeout_per_url=timeout_sec,
        max_urls=fetch_cap,
        retry_count=fetch_retry_count,
        retry_delay_ms=fetch_retry_delay_ms,
    ):
        idx = fetch_idx
        fetch_idx += 1
        fetch_results.append((hit, ctx_md, err))
        url = hit["url"]
        child_id = f"fetch_{idx}"
        child_meta = {"url": url, "title": hit.get("title") or ""}
        async for ev in emitter.yield_begin(
            child_id, name="web_fetch", parent_id="fetch", metadata=child_meta
        ):
            yield ev
        if ctx_md:
            fetch_ok += 1
            block = ctx_md[:MAX_SOURCE_CHARS]
            if not block.lstrip().startswith("##"):
                block = f"## [网页材料] {hit.get('title') or url}\n\n{block}"
            sources_md.append(block)
            title = str(hit.get("title") or "")
            preview = f"已抓取正文（约 {len(ctx_md)} 字）"
            async for ev in _emit_tool(
                "web_fetch",
                {"url": url, "title": title},
                preview,
                trace=execution_trace,
            ):
                yield ev
            append_workflow(
                execution_trace,
                node_id=child_id,
                name="web_fetch",
                state="done",
                title=title,
                url=url,
            )
            async for ev in emitter.yield_finish(
                child_id, "done", name="web_fetch", parent_id="fetch", metadata=child_meta
            ):
                yield ev
        else:
            fetch_failed += 1
            try:
                from urllib.parse import urlparse

                host = urlparse(url).netloc
                if host and host not in failed_hosts:
                    failed_hosts.append(host)
            except Exception:
                pass
            snippet = hit.get("snippet") or ""
            err_msg = err or "抓取失败"
            failed_literature.append(
                {
                    "url": url,
                    "title": str(hit.get("title") or ""),
                    "reason": err_msg,
                    "kind": "抓取网页",
                }
            )
            sources_md.append(
                f"## [网页材料] {hit.get('title') or url}\n\n(抓取失败: {err_msg})\n\n{snippet}\n"
            )
            async for ev in _emit_tool(
                "web_fetch",
                {"url": url, "title": hit.get("title") or ""},
                "",
                error=err_msg,
                trace=execution_trace,
            ):
                yield ev
            append_workflow(
                execution_trace,
                node_id=child_id,
                name="web_fetch",
                state="error",
                title=str(hit.get("title") or ""),
                url=url,
                error=err_msg,
            )
            async for ev in emitter.yield_finish(
                child_id,
                "error",
                name="web_fetch",
                parent_id="fetch",
                metadata={**child_meta, "error": err_msg},
            ):
                yield ev

        label = (hit.get("title") or "").strip() or url
        recent_fetch_labels.append(label[:60])
        if len(recent_fetch_labels) > 5:
            recent_fetch_labels.pop(0)
        if fetch_throttle and fetch_throttle.note_completed():
            progress_ctx = format_fetch_progress_context(
                total=len(fetch_hits),
                completed=fetch_idx,
                ok=fetch_ok,
                failed=fetch_failed,
                recent_labels=recent_fetch_labels,
            )
            async for ev in narrate_phase_stream(
                "D",
                user_message,
                progress_ctx,
                think_acc=think_acc,
                ctx=planner_ctx,
            ):
                yield ev
            fetch_throttle.mark_narrated()

    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "fetch", "done"):
        yield ev
    del t_fetch
    fetch_ctx = format_fetch_context(
        total=fetch_idx,
        ok=fetch_ok,
        failed=fetch_failed,
        failed_hosts=failed_hosts,
    )
    async for ev in narrate_phase_stream(
        "E",
        user_message,
        fetch_ctx,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        yield ev
    yield ("stage", {"name": "抓取网页", "state": "done"})
    upsert_stage(execution_trace, "抓取网页", "done")

    yield ("stage", {"name": "引用抽取", "state": "active"})
    t_cite = time.monotonic()
    async for ev in emit_system_think_line(
        f"正在抽取 {fmt_label} 引用元数据…",
        accumulator=think_acc,
    ):
        yield ev
    async for ev in _sync_graph_node(
        emitter, g, graph_artifact_id, "cite_extract", "active"
    ):
        yield ev

    session_title = str(session_meta.get("title") or "")
    cite_records = await extract_and_persist_batch(
        fetch_hits,
        jina_api_key=jina_key or None,
        timeout=timeout_sec,
        max_items=fetch_cap,
        citation_format=citation_format,
        session_id=session_id,
        session_title=session_title,
    )
    for rec in cite_records:
        if rec.success:
            async for ev in _emit_tool(
                "extract_citation",
                {"url": rec.url},
                f"{rec.title} ({rec.year or 'n.d.'}) — {rec.authors or 'Unknown'}",
                trace=execution_trace,
            ):
                yield ev
        else:
            failed_literature.append(
                {
                    "url": rec.url,
                    "title": str(rec.title or ""),
                    "reason": str(rec.error or "引用抽取失败"),
                    "kind": "引用抽取",
                }
            )
            async for ev in _emit_tool(
                "extract_citation",
                {"url": rec.url, "title": rec.title or ""},
                "",
                error=rec.error or "引用抽取失败",
                trace=execution_trace,
            ):
                yield ev

    ref_text = get_store().read_ref_list()
    if ref_text.strip():
        sources_md.append(f"## [Citations] 已收录引用\n\n{ref_text[-8000:]}\n")

    cite_ok = sum(1 for r in cite_records if r.success)
    cite_ctx = format_cite_context(cite_records, fmt_label=fmt_label)
    async for ev in narrate_phase_stream(
        "F",
        user_message,
        cite_ctx,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        yield ev

    async for ev in _sync_graph_node(
        emitter, g, graph_artifact_id, "cite_extract", "done"
    ):
        yield ev
    del t_cite
    yield ("stage", {"name": "引用抽取", "state": "done"})
    upsert_stage(execution_trace, "引用抽取", "done")

    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "generate", "active"):
        yield ev
    yield ("stage", {"name": "综述生成", "state": "active"})
    t_generate = time.monotonic()

    gen_ctx = format_generate_context(
        source_blocks=len(sources_md),
        cite_ok=cite_ok,
        failed_fetch=fetch_failed,
        fmt_label=fmt_label,
    )
    async for ev in narrate_phase_stream(
        "G",
        user_message,
        gen_ctx,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        yield ev

    context_block = "\n".join(sources_md)[:80_000]
    gen_prompt = f"""用户研究问题：{user_message}

【多源材料】
{context_block}
"""
    main_parts: list[str] = []
    async for chunk in llm.chat_stream(
        [LLMMessage(role="user", content=gen_prompt)],
        system=_generate_system_prompt(citation_format),
        max_tokens=4096,
        temperature=0.35,
    ):
        main_parts.append(chunk)
        yield ("text", {"delta": chunk})

    raw_main = "".join(main_parts)
    main_text = append_compliance_footer(raw_main)
    if main_text != raw_main:
        tail = main_text[len(raw_main) :]
        if tail:
            yield ("text", {"delta": tail})

    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "generate", "done"):
        yield ev
    del t_generate
    yield ("stage", {"name": "综述生成", "state": "done"})
    upsert_stage(execution_trace, "综述生成", "done")

    t_deliver = time.monotonic()
    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "deliver", "active"):
        yield ev

    store.save_review_artifact(session_id, main_text)
    art_id = _new_id("review")
    yield (
        "artifact",
        {
            "id": art_id,
            "lang": "markdown",
            "delta": main_text,
            "done": True,
        },
    )

    async for ev in _sync_graph_node(emitter, g, graph_artifact_id, "deliver", "done"):
        yield ev
    del t_deliver

    upsert_stage(execution_trace, "完成", "done")
    think_text = think_acc.finalize()
    if think_text:
        execution_trace["thinkContent"] = think_text

    lib_result = upsert_library_from_run(
        session_id,
        fetch_results=fetch_results,
        cite_records=cite_records,
        failed_literature=failed_literature,
        review_text=main_text,
        citation_format=citation_format,
        session_title=session_title,
    )
    yield (
        "extension",
        {
            "name": "library_updated",
            "version": "1.0",
            "data": lib_result,
        },
    )

    msg_meta: dict[str, Any] = {"execution_trace": execution_trace}
    if think_text:
        msg_meta["think"] = think_text
    if failed_literature:
        msg_meta["failed_literature"] = failed_literature
    msg_meta["library_item_ids"] = lib_result.get("item_ids") or []
    store.append_message(session_id, "assistant", main_text, meta=msg_meta)
    yield ("stage", {"name": "完成", "state": "done"})
