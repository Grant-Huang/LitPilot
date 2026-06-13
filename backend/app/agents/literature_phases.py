"""Reusable literature workflow phase runners for multi-turn sessions."""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.execution_trace import append_tool, append_workflow, record_literature_stats, upsert_stage
from app.agents.literature_planner import (
    format_cite_context,
    format_fetch_context,
    format_fetch_progress_context,
    format_generate_context,
    format_search_before_context,
    format_search_context,
    narrate_phase_stream,
    should_narrate,
)
from app.agents.literature_progress import iter_progress_while_pending
from app.agents.literature_source import build_fetch_hits
from app.agents.parallel_fetch import iter_fetch_sources_parallel
from app.agents.retry_utils import retry_async
from app.agents.session_corpus import SessionCorpus, hits_from_urls
from app.agents.tools.cached_tools import cached_web_search
from app.agents.research_decompose import format_pass_query_label
from app.agents.tools.search_hits import (
    ACADEMIC_SEARCH_DOMAINS,
    DEFAULT_EXCLUDE_DOMAINS,
    apply_literature_hit_filters,
    normalize_search_results,
)
from app.agents.url_list import resolve_fetch_display_title
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.skills.citation_extractor import extract_and_persist_batch

MAX_SOURCE_CHARS = 14_000


async def emit_tool_event(
    new_id_fn,
    name: str,
    args: dict[str, Any],
    output: str,
    *,
    error: str | None = None,
    duration_ms: int | None = None,
    trace: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    tid = new_id_fn("tc")
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
        from app.agents.execution_trace import append_tool

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


async def stream_search_phase(
    *,
    user_message: str,
    query: str,
    search_api_key: str,
    search_max_results: int,
    search_retry_count: int,
    fetch_retry_delay_ms: int,
    source_mode: str,
    upload_count: int,
    skip_web_search: bool,
    upload_urls: list[str],
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    corpus: SessionCorpus | None = None,
    result: dict[str, Any] | None = None,
    search_include_domains: tuple[str, ...] | None = None,
    search_exclude_domains: tuple[str, ...] | None = None,
    search_depth: str = "advanced",
    search_enforce_domain_filter: bool = True,
    search_enable_junk_filter: bool = True,
    exclude_title_substrings: list[str] | None = None,
    pass_index: int = 1,
    pass_total: int = 1,
    topic_title: str = "",
    emit_stage_lifecycle: bool = True,
    search_provider: str | None = None,
    emit_pass_hits: bool = False,
    source_queries: dict[str, str] | None = None,
    skip_sources: frozenset[str] | None = None,
    source_locks: dict[str, asyncio.Lock] | None = None,
    seen_source_hits: set[str] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.tools.web_providers import normalize_search_provider

    if search_provider is None:
        from app.agents.agent_settings import get_web_search_provider

        search_provider = await get_web_search_provider()
    search_prov = normalize_search_provider(search_provider)
    include_domains = search_include_domains or ACADEMIC_SEARCH_DOMAINS
    exclude_domains = search_exclude_domains or DEFAULT_EXCLUDE_DOMAINS
    search_depth = search_depth if search_depth in ("basic", "advanced") else "advanced"
    hits: list[dict[str, str]] = []
    answer = ""
    out = result if result is not None else {}
    search_failed = False

    if emit_stage_lifecycle and pass_index == 1:
        yield ("stage", {"name": "文献检索", "state": "active"})

    if skip_web_search:
        async for ev in emit_system_think_line(
            f"已跳过 web_search 网络检索（用户列表 {upload_count} 条）。",
            accumulator=think_acc,
        ):
            yield ev
        yield ("stage", {"name": "文献检索", "state": "done"})
        upsert_stage(execution_trace, "文献检索", "done")
        out["hits"] = hits
        out["answer"] = answer
        return

    label = format_pass_query_label(query)
    if pass_total > 1:
        async for ev in emit_system_think_line(
            f"第 {pass_index}/{pass_total} 轮检索：{label}",
            accumulator=think_acc,
        ):
            yield ev
    if pass_index == 1:
        search_before_ctx = format_search_before_context(
            query=query,
            source_mode=source_mode,
            search_max_results=search_max_results,
            upload_count=upload_count,
            skipped_web_search=False,
            search_provider=search_prov,
        )
        async for ev in narrate_phase_stream(
            "B",
            user_message,
            search_before_ctx,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            yield ev

    pre_corpus_hit_count = 0
    try:
        pass_meta = {
            "query": query,
            "pass_index": pass_index,
            "pass_total": pass_total,
            "provider": search_prov,
            "topic_title": topic_title or "",
        }
        yield ("literature_search_pass_start", dict(pass_meta))

        t0 = time.monotonic()
        raw_search: dict[str, Any] = {"results": [], "answer": "", "source_counts": {}}

        if search_prov == "multi_academic":
            from app.agents.tools.providers import multi_academic as multi_academic_provider
            from app.agents.tools.web_providers import _resolve_s2_api_key

            s2_key = await _resolve_s2_api_key(None)
            ma_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
            source_total = len(multi_academic_provider.SOURCE_LABELS)
            sources_done = 0

            async def _ma_worker() -> dict[str, Any]:
                merged: dict[str, Any] = {
                    "results": [],
                    "answer": "",
                    "source_counts": {},
                }
                async for kind, payload in multi_academic_provider.iter_search_events(
                    query,
                    max_results=search_max_results,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    s2_api_key=s2_key or "",
                    source_queries=source_queries,
                    skip_sources=skip_sources,
                    source_locks=source_locks,
                    seen_source_hits=seen_source_hits,
                    search_retry_count=search_retry_count,
                    search_retry_delay_ms=fetch_retry_delay_ms,
                ):
                    if kind == "source_start":
                        await ma_queue.put(
                            ("literature_search_source_start", {**pass_meta, **payload}),
                        )
                    elif kind == "source_done":
                        await ma_queue.put(
                            ("literature_search_source_done", {**pass_meta, **payload}),
                        )
                    elif kind == "complete":
                        merged = payload
                return merged

            ma_task = asyncio.create_task(_ma_worker())
            try:
                while True:
                    if ma_task.done() and ma_queue.empty():
                        break
                    try:
                        item = await asyncio.wait_for(ma_queue.get(), timeout=5.0)
                    except asyncio.TimeoutError:
                        detail = topic_title or format_pass_query_label(query)
                        yield (
                            "literature_progress",
                            {
                                "stage": "search",
                                "detail": detail,
                                "elapsed_ms": int((time.monotonic() - t0) * 1000),
                                "pass_index": pass_index,
                                "pass_total": pass_total,
                                "provider": search_prov,
                                "completed": sources_done,
                                "total": source_total,
                            },
                        )
                        continue
                    if item is None:
                        break
                    ev_name, ev_data = item
                    if ev_name == "literature_search_source_done":
                        sources_done += 1
                    yield (ev_name, ev_data)
                    yield (
                        "literature_progress",
                        {
                            "stage": "search",
                            "detail": str(ev_data.get("label") or ev_data.get("source") or ""),
                            "elapsed_ms": int((time.monotonic() - t0) * 1000),
                            "pass_index": pass_index,
                            "pass_total": pass_total,
                            "source": ev_data.get("source"),
                            "completed": sources_done,
                            "total": source_total,
                        },
                    )
                raw_search = await ma_task
            finally:
                if not ma_task.done():
                    ma_task.cancel()
                    await asyncio.gather(ma_task, return_exceptions=True)
        else:
            async def _search_call() -> dict:
                return await cached_web_search(
                    search_api_key,
                    query,
                    provider=search_prov,
                    max_results=search_max_results,
                    search_depth=search_depth,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                )

            search_task = asyncio.create_task(
                retry_async(
                    _search_call,
                    max_retries=search_retry_count,
                    delay_ms=fetch_retry_delay_ms,
                )
            )
            query_label = format_pass_query_label(query) if query.strip() else "检索"
            async for tick in iter_progress_while_pending(
                "search",
                query_label,
                search_task,
                pass_index=pass_index,
                pass_total=pass_total,
                provider=search_prov,
            ):
                yield tick
            raw_search = await search_task

        search_ms = int((time.monotonic() - t0) * 1000)
        raw_hits = normalize_search_results(raw_search)
        hits, filter_warning = apply_literature_hit_filters(
            raw_hits,
            include_domains=include_domains,
            enable_junk_filter=search_enable_junk_filter,
            enforce_domain_filter=search_enforce_domain_filter,
            exclude_title_substrings=exclude_title_substrings,
        )
        if filter_warning:
            async for ev in emit_system_think_line(
                filter_warning,
                accumulator=think_acc,
            ):
                yield ev
        answer = str(raw_search.get("answer") or "").strip()

        pre_corpus_hit_count = len(hits)
        if corpus:
            hits = [h for h in hits if not corpus.has_url(str(h.get("url") or ""))]

        async for ev in emit_tool_event(
            lambda p: f"{p}_search",
            "web_search",
            {
                "query": query,
                "provider": search_prov,
                "pass_index": pass_index,
                "pass_total": pass_total,
            },
            json.dumps(
                {
                    "answer": answer[:500],
                    "hits": len(hits),
                    "hits_before_corpus": pre_corpus_hit_count,
                    "retries": search_retry_count,
                },
                ensure_ascii=False,
            ),
            duration_ms=search_ms,
            trace=execution_trace,
        ):
            yield ev
        # 工具条已展示命中后立刻落盘，避免后续 narrate/异常导致 pass_out 丢失
        out["hits"] = [dict(h) for h in hits]
        out["answer"] = answer
        out["tool_hit_count"] = len(hits)
        out["hits_before_corpus"] = pre_corpus_hit_count
        if emit_pass_hits and hits:
            yield (
                "literature_search_pass_hits",
                {
                    "hits": out["hits"],
                    "pass_index": pass_index,
                    "pass_total": pass_total,
                },
            )
        yield (
            "literature_search_pass_done",
            {
                **pass_meta,
                "hits": len(hits),
                "hits_found": int(raw_search.get("raw_found_total") or pre_corpus_hit_count),
                "hits_taken": len(hits),
                "source_counts": raw_search.get("source_counts") or {},
                "duration_ms": search_ms,
            },
        )
    except Exception:
        search_failed = True
        if not upload_urls:
            raise
        async for ev in emit_system_think_line(
            f"web_search（{search_prov}）检索失败，将仅使用用户链接（{len(upload_urls)} 条）。",
            accumulator=think_acc,
        ):
            yield ev
    else:
        # 多轮分主题检索：单轮 0 命中不终止，合并后再判定（避免第 4/4 轮空结果丢掉前 3 轮命中）
        if (
            pass_total == 1
            and not hits
            and not answer
            and not upload_urls
        ):
            async for ev in emit_system_think_line(
                "单轮检索无命中（pass_hit_counts=[0]，未进入合并阶段）。",
                accumulator=think_acc,
            ):
                yield ev
            raise ValueError("未检索到可用文献结果，本次会话已终止。")
        if pass_total > 1 and not hits and not answer:
            async for ev in emit_system_think_line(
                f"第 {pass_index}/{pass_total} 轮未命中，继续下一子主题。",
                accumulator=think_acc,
            ):
                yield ev

    if not search_failed and "hits" not in out:
        out["hits"] = [dict(h) for h in hits]
        out["answer"] = answer
        out["tool_hit_count"] = len(hits)

    if pass_index == pass_total and pass_total == 1:
        search_ctx = format_search_context(hits, answer, query=query)
        async for ev in narrate_phase_stream(
            "C",
            user_message,
            search_ctx,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            yield ev
        if emit_stage_lifecycle:
            yield ("stage", {"name": "文献检索", "state": "done"})
            upsert_stage(execution_trace, "文献检索", "done")


async def _stream_expanded_multi_academic_by_source(
    *,
    user_message: str,
    clean_queries: list[str],
    titles: list[str],
    total: int,
    search_max_results: int,
    search_retry_count: int,
    fetch_retry_delay_ms: int,
    source_mode: str,
    upload_count: int,
    upload_urls: list[str],
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    corpus: SessionCorpus | None,
    search_include_domains: tuple[str, ...] | None,
    search_exclude_domains: tuple[str, ...] | None,
    search_enforce_domain_filter: bool,
    search_enable_junk_filter: bool,
    exclude_title_substrings: list[str] | None,
    search_sub_topics: list[Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Multi-topic multi_academic: parallel across sources, one in-flight request per source."""
    from app.agents.tools.providers import multi_academic as ma
    from app.agents.tools.web_providers import _resolve_s2_api_key
    from app.agents.search_aspects import sub_topic_pass_spec
    from app.schemas.literature_outline import ResearchSubTopic

    include_domains = search_include_domains or ACADEMIC_SEARCH_DOMAINS
    exclude_domains = search_exclude_domains or DEFAULT_EXCLUDE_DOMAINS

    yield ("stage", {"name": "文献检索", "state": "active"})

    if clean_queries:
        search_before_ctx = format_search_before_context(
            query=clean_queries[0],
            source_mode=source_mode,
            search_max_results=search_max_results,
            upload_count=upload_count,
            skipped_web_search=False,
            search_provider="multi_academic",
        )
        async for ev in narrate_phase_stream(
            "B",
            user_message,
            search_before_ctx,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            yield ev

    specs: list[ma.PassSpec] = []
    spec_count = len(search_sub_topics) if search_sub_topics else len(clean_queries)
    if search_sub_topics:
        for idx, st in enumerate(search_sub_topics, start=1):
            if not isinstance(st, ResearchSubTopic):
                continue
            fallback, sq, skip = sub_topic_pass_spec(st)
            specs.append(
                ma.PassSpec(
                    pass_index=idx,
                    pass_total=spec_count,
                    query=fallback,
                    topic_title=str(
                        st.title or (titles[idx - 1] if idx - 1 < len(titles) else "")
                    ),
                    max_results=search_max_results,
                    source_queries=sq,
                    skip_sources=skip,
                )
            )
    if not specs:
        specs = [
            ma.PassSpec(
                pass_index=idx,
                pass_total=spec_count,
                query=query,
                topic_title=titles[idx - 1] if idx - 1 < len(titles) else "",
                max_results=search_max_results,
            )
            for idx, query in enumerate(clean_queries, start=1)
        ]

    for spec in specs:
        yield (
            "literature_search_pass_start",
            {
                "query": spec.query,
                "pass_index": spec.pass_index,
                "pass_total": spec.pass_total,
                "provider": "multi_academic",
                "topic_title": spec.topic_title,
            },
        )

    s2_key = await _resolve_s2_api_key(None)
    t0 = time.monotonic()
    pass_outcomes: dict[int, dict[str, Any]] = {}

    async for kind, payload in ma.iter_multi_pass_by_source_events(
        specs,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        s2_api_key=s2_key or "",
        search_retry_count=search_retry_count,
        search_retry_delay_ms=fetch_retry_delay_ms,
    ):
        if kind == "source_start":
            yield ("literature_search_source_start", payload)
            yield (
                "literature_progress",
                {
                    "stage": "search",
                    "detail": str(payload.get("label") or payload.get("source") or ""),
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "pass_index": payload.get("pass_index"),
                    "pass_total": payload.get("pass_total"),
                    "source": payload.get("source"),
                },
            )
        elif kind == "source_done":
            yield ("literature_search_source_done", payload)
            yield (
                "literature_progress",
                {
                    "stage": "search",
                    "detail": str(payload.get("label") or payload.get("source") or ""),
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                    "pass_index": payload.get("pass_index"),
                    "pass_total": payload.get("pass_total"),
                    "source": payload.get("source"),
                },
            )
        elif kind == "pass_complete":
            pass_index = int(payload.get("pass_index") or 0)
            pass_total = int(payload.get("pass_total") or total)
            query = str(payload.get("query") or "")
            topic_title = str(payload.get("topic_title") or "")
            raw_search = {
                "results": payload.get("results") or [],
                "answer": "",
                "source_counts": payload.get("source_counts") or {},
                "raw_found_total": payload.get("raw_found_total") or 0,
                "hits_taken": payload.get("hits_taken") or 0,
            }
            pass_meta = {
                "query": query,
                "pass_index": pass_index,
                "pass_total": pass_total,
                "provider": "multi_academic",
                "topic_title": topic_title,
            }
            raw_hits = normalize_search_results(raw_search)
            hits, filter_warning = apply_literature_hit_filters(
                raw_hits,
                include_domains=include_domains,
                enable_junk_filter=search_enable_junk_filter,
                enforce_domain_filter=search_enforce_domain_filter,
                exclude_title_substrings=exclude_title_substrings,
            )
            if filter_warning:
                async for ev in emit_system_think_line(
                    filter_warning,
                    accumulator=think_acc,
                ):
                    yield ev
            pre_corpus_hit_count = len(hits)
            if corpus:
                hits = [h for h in hits if not corpus.has_url(str(h.get("url") or ""))]
            search_ms = int((time.monotonic() - t0) * 1000)
            async for ev in emit_tool_event(
                lambda p: f"{p}_search",
                "web_search",
                {
                    "query": query,
                    "provider": "multi_academic",
                    "pass_index": pass_index,
                    "pass_total": pass_total,
                },
                json.dumps(
                    {
                        "answer": "",
                        "hits": len(hits),
                        "hits_before_corpus": pre_corpus_hit_count,
                        "retries": search_retry_count,
                    },
                    ensure_ascii=False,
                ),
                duration_ms=search_ms,
                trace=execution_trace,
            ):
                yield ev
            pass_out = {
                "hits": [dict(h) for h in hits],
                "answer": "",
                "tool_hit_count": len(hits),
                "hits_before_corpus": pre_corpus_hit_count,
            }
            pass_outcomes[pass_index] = pass_out
            yield (
                "literature_search_pass_hits",
                {
                    "hits": pass_out["hits"],
                    "pass_index": pass_index,
                    "pass_total": pass_total,
                },
            )
            yield (
                "literature_search_pass_done",
                {
                    **pass_meta,
                    "hits": len(hits),
                    "hits_found": int(raw_search.get("raw_found_total") or pre_corpus_hit_count),
                    "hits_taken": len(hits),
                    "source_counts": raw_search.get("source_counts") or {},
                    "duration_ms": search_ms,
                },
            )
            if not hits:
                async for ev in emit_system_think_line(
                    f"第 {pass_index}/{pass_total} 轮未命中，继续下一子主题。",
                    accumulator=think_acc,
                ):
                    yield ev

    # Stash for caller via execution_trace scratch (avoid changing signature)
    execution_trace["_ma_pass_outcomes"] = pass_outcomes

async def stream_fetch_phase(
    *,
    user_message: str,
    fetch_hits: list[dict[str, str]],
    fetch_cap: int,
    fetch_api_key: str | None,
    fetch_provider: str | None = None,
    llm,
    parallel: int,
    timeout_sec: float,
    fetch_retry_count: int,
    fetch_retry_delay_ms: int,
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    emitter,
    graph,
    graph_artifact_id: str,
    sync_graph_node,
    search_answer: str = "",
    result: dict[str, Any] | None = None,
    max_source_chars: int = MAX_SOURCE_CHARS,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.agent_settings import get_web_fetch_provider
    from app.agents.tools.web_providers import normalize_fetch_provider
    from app.agents.workflow_graph import apply_fetch_provider_label

    if fetch_provider is None:
        fetch_provider = await get_web_fetch_provider()
    fetch_provider = normalize_fetch_provider(fetch_provider)
    apply_fetch_provider_label(graph, fetch_provider)
    out = result if result is not None else {}
    delta = SessionCorpus()
    if search_answer:
        delta.append_search_answer(search_answer)
    # Capture delta reference before fetch loop so partial data survives exceptions
    out["delta"] = delta

    yield ("stage", {"name": "抓取网页", "state": "active"})
    upload_n = sum(1 for h in fetch_hits if str(h.get("source") or "") == "upload")
    search_n = len(fetch_hits) - upload_n
    queue_parts = []
    if upload_n:
        queue_parts.append(f"用户上传 {upload_n} 条")
    if search_n:
        queue_parts.append(f"检索命中 {search_n} 条")
    queue_desc = "、".join(queue_parts) if queue_parts else "0 条"
    async for ev in emit_system_think_line(
        f"开始并行 web_fetch（{fetch_provider}）：{queue_desc}，队列共 {len(fetch_hits)} 篇（上限 {fetch_cap}）。",
        accumulator=think_acc,
    ):
        yield ev
    async for ev in sync_graph_node(emitter, graph, graph_artifact_id, "fetch", "active"):
        yield ev

    fetch_idx = 0
    fetch_ok = 0
    fetch_failed = 0
    failed_hosts: list[str] = []
    recent_fetch_labels: list[str] = []

    upload_queue = [h for h in fetch_hits if str(h.get("source") or "") == "upload"]
    search_queue = [h for h in fetch_hits if str(h.get("source") or "") != "upload"]
    ordered_queues = [upload_queue, search_queue] if upload_queue else [fetch_hits]

    fetch_total = min(len(fetch_hits), fetch_cap)
    url_to_idx: dict[str, int] = {}

    for queue in ordered_queues:
        if not queue:
            continue
        async for phase, hit, ctx_md, err in iter_fetch_sources_parallel(
            queue,
            api_key=fetch_api_key or None,
            llm=llm,
            parallel=parallel,
            timeout_per_url=timeout_sec,
            max_urls=fetch_cap,
            retry_count=fetch_retry_count,
            retry_delay_ms=fetch_retry_delay_ms,
            fetch_provider=fetch_provider,
        ):
            if phase == "tick":
                yield (
                    "literature_progress",
                    {
                        "stage": "fetch",
                        "detail": f"抓取中 {fetch_ok + fetch_failed}/{fetch_total}",
                        "completed": fetch_ok + fetch_failed,
                        "total": fetch_total,
                        "in_flight": max(0, fetch_idx - fetch_ok - fetch_failed),
                        "parallel": parallel,
                    },
                )
                continue
            url = str(hit.get("url") or "")
            if phase == "start":
                idx = fetch_idx
                fetch_idx += 1
                url_to_idx[url] = idx
                display_title = resolve_fetch_display_title(hit, "")
                child_id = f"fetch_{idx}"
                child_meta = {
                    "url": url,
                    "title": hit.get("title") or "",
                    "provider": fetch_provider,
                }
                yield (
                    "literature_fetch_start",
                    {
                        "url": url,
                        "title": display_title or str(hit.get("title") or ""),
                        "index": idx,
                        "total": fetch_total,
                        "provider": fetch_provider,
                    },
                )
                async for ev in emitter.yield_begin(
                    child_id, name="web_fetch", parent_id="fetch", metadata=child_meta
                ):
                    yield ev
                yield (
                    "literature_progress",
                    {
                        "stage": "fetch",
                        "detail": display_title or url,
                        "elapsed_ms": 0,
                        "completed": max(0, idx - 1),
                        "total": fetch_total,
                        "in_flight": min(parallel, fetch_total - idx + 1),
                        "parallel": parallel,
                    },
                )
                continue

            idx = url_to_idx.pop(url, fetch_idx)
            delta.fetch_results.append((hit, ctx_md or "", err))
            delta.fetch_hits.append(hit)
            delta.register_url(url)

            child_id = f"fetch_{idx}"
            child_meta = {
                "url": url,
                "title": hit.get("title") or "",
                "provider": fetch_provider,
            }

            display_title = resolve_fetch_display_title(hit, ctx_md or "")
            if ctx_md:
                fetch_ok += 1
                block = ctx_md[:max_source_chars]
                if not block.lstrip().startswith("##"):
                    header = display_title or hit.get("title") or url
                    block = f"## [网页材料] {header}\n\n{block}"
                delta.sources_md.append(block)
                char_count = len(ctx_md)
                preview = f"已抓取正文（约 {char_count} 字）"
                async for ev in emit_tool_event(
                    lambda p, i=idx: f"{p}_{i}",
                    "web_fetch",
                    {"url": url, "title": display_title, "char_count": char_count, "provider": fetch_provider},
                    preview,
                    trace=execution_trace,
                ):
                    yield ev
                append_workflow(
                    execution_trace,
                    node_id=child_id,
                    name="web_fetch",
                    state="done",
                    title=display_title,
                    url=url,
                    char_count=char_count,
                )
                child_meta["title"] = display_title
                child_meta["char_count"] = char_count
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
                delta.failed_literature.append(
                    {
                        "url": url,
                        "title": display_title or str(hit.get("title") or ""),
                        "reason": err_msg,
                        "kind": "抓取网页",
                    }
                )
                fail_header = display_title or hit.get("title") or url
                delta.sources_md.append(
                    f"## [网页材料] {fail_header}\n\n(抓取失败: {err_msg})\n\n{snippet}\n"
                )
                async for ev in emit_tool_event(
                    lambda p, i=idx: f"{p}_{i}",
                    "web_fetch",
                    {"url": url, "title": display_title, "provider": fetch_provider},
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
                    title=display_title,
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

            label = display_title or (hit.get("title") or "").strip() or url
            recent_fetch_labels.append(label[:60])
            if len(recent_fetch_labels) > 5:
                recent_fetch_labels.pop(0)
            done_count = fetch_ok + fetch_failed
            yield (
                "literature_progress",
                {
                    "stage": "fetch",
                    "detail": f"{done_count}/{fetch_total} 篇",
                    "completed": done_count,
                    "total": fetch_total,
                    "ok": fetch_ok,
                    "failed": fetch_failed,
                    "parallel": parallel,
                },
            )

    async for ev in sync_graph_node(emitter, graph, graph_artifact_id, "fetch", "done"):
        yield ev

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
    out["delta"] = delta
    out["fetch_ok"] = fetch_ok
    out["fetch_failed"] = fetch_failed


async def stream_cite_phase(
    *,
    user_message: str,
    fetch_hits: list[dict[str, str]],
    fetch_cap: int,
    fetch_api_key: str | None,
    timeout_sec: float,
    citation_format: str,
    fmt_label: str,
    session_id: str,
    session_title: str,
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    emitter,
    graph,
    graph_artifact_id: str,
    sync_graph_node,
    store,
    failed_literature: list[dict[str, str]],
    result: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    out = result if result is not None else {}
    yield ("stage", {"name": "引用抽取", "state": "active"})
    async for ev in emit_system_think_line(
        f"正在并行抽取 {fmt_label} 引用并补全 DOI / 被引 / 他引（OpenAlex + Crossref）…",
        accumulator=think_acc,
    ):
        yield ev
    async for ev in sync_graph_node(
        emitter, graph, graph_artifact_id, "cite_extract", "active"
    ):
        yield ev

    cite_records = await extract_and_persist_batch(
        fetch_hits,
        fetch_api_key=fetch_api_key or None,
        timeout=timeout_sec,
        max_items=fetch_cap,
        citation_format=citation_format,
        session_id=session_id,
        session_title=session_title,
    )
    for rec in cite_records:
        if rec.success:
            async for ev in emit_tool_event(
                lambda p: f"{p}_cite",
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
            async for ev in emit_tool_event(
                lambda p: f"{p}_cite",
                "extract_citation",
                {"url": rec.url, "title": rec.title or ""},
                "",
                error=rec.error or "引用抽取失败",
                trace=execution_trace,
            ):
                yield ev

    ref_text = store.read_ref_list()
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

    async for ev in sync_graph_node(
        emitter, graph, graph_artifact_id, "cite_extract", "done"
    ):
        yield ev
    yield ("stage", {"name": "引用抽取", "state": "done"})
    upsert_stage(execution_trace, "引用抽取", "done")
    out["cite_records"] = cite_records
    out["ref_text"] = ref_text
    out["cite_ok"] = cite_ok


def build_fetch_queue(
    *,
    source_mode: str,
    hits: list[dict[str, str]],
    user_urls: list[str],
    fetch_cap: int,
    skip_reason: str | None = None,
):
    from app.agents.literature_source import build_fetch_hits

    if user_urls and not hits:
        result = build_fetch_hits(
            "user_only",
            [],
            user_urls,
            max_urls=fetch_cap,
        )
    else:
        result = build_fetch_hits(source_mode, hits, user_urls, max_urls=fetch_cap)
    if skip_reason and not result.skip_reason:
        result.skip_reason = skip_reason
    return result


def user_url_hits(urls: list[str]) -> list[dict[str, str]]:
    return hits_from_urls(urls)


OUTLINE_ARTIFACT_LANG = "literature-outline+json"
