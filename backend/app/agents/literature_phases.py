"""Reusable literature workflow phase runners for multi-turn sessions."""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from app.agents.execution_trace import append_tool, append_workflow, upsert_stage
from app.agents.literature_planner import (
    FetchNarrationThrottle,
    format_cite_context,
    format_fetch_context,
    format_fetch_progress_context,
    format_generate_context,
    format_search_before_context,
    format_search_context,
    narrate_phase_stream,
    should_narrate,
)
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
    emit_stage_lifecycle: bool = True,
    search_provider: str | None = None,
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
    elif pass_total > 1:
        label = format_pass_query_label(query)
        async for ev in emit_system_think_line(
            f"⟦sys⟧第 {pass_index}/{pass_total} 轮检索：{label}⟦/sys⟧",
            accumulator=think_acc,
        ):
            yield ev

    pre_corpus_hit_count = 0
    try:

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

        t0 = time.monotonic()
        raw_search = await retry_async(
            _search_call,
            max_retries=search_retry_count,
            delay_ms=fetch_retry_delay_ms,
        )
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
                f"⟦sys⟧{filter_warning}⟦/sys⟧",
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
                "⟦sys⟧单轮检索无命中（pass_hit_counts=[0]，未进入合并阶段）。⟦/sys⟧",
                accumulator=think_acc,
            ):
                yield ev
            raise ValueError("未检索到可用文献结果，本次会话已终止。")
        if pass_total > 1 and not hits and not answer:
            async for ev in emit_system_think_line(
                f"⟦sys⟧第 {pass_index}/{pass_total} 轮未命中，继续下一子主题。⟦/sys⟧",
                accumulator=think_acc,
            ):
                yield ev

    if not search_failed and "hits" not in out:
        out["hits"] = [dict(h) for h in hits]
        out["answer"] = answer
        out["tool_hit_count"] = len(hits)

    if pass_index == pass_total:
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


async def stream_expanded_search_phase(
    *,
    user_message: str,
    queries: list[str],
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
    search_provider: str | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.search_merge import merge_search_hits

    out = result if result is not None else {}
    clean_queries = [q.strip() for q in queries if q and q.strip()]
    if not clean_queries:
        clean_queries = [""]
    total = len(clean_queries)
    per_query_max = max(2, search_max_results // total)
    hits_lists: list[list[dict[str, str]]] = []
    answers: list[str] = []
    raw_total = 0
    raw_before_corpus = 0
    tool_hit_total = 0

    yield (
        "literature_search_plan",
        {
            "queries": clean_queries,
            "per_query_max_results": per_query_max,
            "total_passes": total,
        },
    )

    for idx, query in enumerate(clean_queries, start=1):
        pass_out: dict[str, Any] = {}
        async for ev in stream_search_phase(
            user_message=user_message,
            query=query,
            search_api_key=search_api_key,
            search_max_results=per_query_max,
            search_retry_count=search_retry_count,
            fetch_retry_delay_ms=fetch_retry_delay_ms,
            source_mode=source_mode,
            upload_count=upload_count if idx == 1 else 0,
            skip_web_search=skip_web_search,
            upload_urls=upload_urls if idx == 1 else [],
            think_acc=think_acc,
            planner_ctx=planner_ctx,
            execution_trace=execution_trace,
            corpus=corpus,
            result=pass_out,
            search_include_domains=search_include_domains,
            search_exclude_domains=search_exclude_domains,
            search_depth=search_depth,
            search_enforce_domain_filter=search_enforce_domain_filter,
            search_enable_junk_filter=search_enable_junk_filter,
            exclude_title_substrings=exclude_title_substrings,
            pass_index=idx,
            pass_total=total,
            emit_stage_lifecycle=idx == 1 or idx == total,
            search_provider=search_provider,
        ):
            yield ev
        pass_hits = [dict(h) for h in (pass_out.get("hits") or [])]
        raw_total += len(pass_hits)
        raw_before_corpus += int(pass_out.get("hits_before_corpus") or len(pass_hits))
        tool_hit_total += int(pass_out.get("tool_hit_count") or len(pass_hits))
        hits_lists.append(pass_hits)
        ans = str(pass_out.get("answer") or "").strip()
        if ans:
            answers.append(ans)

    merge_cap = search_max_results if search_max_results > 0 else None
    pass_hit_counts = [len(h) for h in hits_lists]
    merged_pre_corpus = merge_search_hits(hits_lists, max_results=merge_cap)
    merged = list(merged_pre_corpus)
    corpus_dropped = 0
    if corpus:
        before = len(merged)
        merged = [h for h in merged if not corpus.has_url(str(h.get("url") or ""))]
        corpus_dropped = before - len(merged)

    yield (
        "literature_search_merge",
        {
            "raw_total": raw_total,
            "raw_before_corpus": raw_before_corpus,
            "tool_hit_total": tool_hit_total,
            "deduped": len(merged),
            "deduped_pre_corpus": len(merged_pre_corpus),
            "corpus_dropped": corpus_dropped,
            "cap": search_max_results,
            "pass_hit_counts": pass_hit_counts,
        },
    )

    combined_answer = " ".join(answers).strip()
    has_existing_material = bool(
        corpus
        and (corpus.fetch_hits or corpus.sources_md or corpus.known_url_keys)
    )
    # 以各轮 pass_out 合计为准；避免「工具条显示有命中、合并后误判为 0」
    if (
        not merged
        and not combined_answer
        and not upload_urls
        and raw_total <= 0
        and tool_hit_total <= 0
        and not has_existing_material
    ):
        diag = (
            f"pass_hit_counts={pass_hit_counts}，raw_total={raw_total}，"
            f"tool_hit_total={tool_hit_total}，raw_before_corpus={raw_before_corpus}，"
            f"deduped={len(merged)}，deduped_pre_corpus={len(merged_pre_corpus)}，"
            f"corpus_dropped={corpus_dropped}"
        )
        async for ev in emit_system_think_line(
            f"⟦sys⟧检索合并后无可用命中（{diag}）。"
            "若 pass_hit_counts 全 0 而工具条有命中，属 pass_out 未写入；"
            "若 raw_total>0 且 deduped=0，属语料去重或 URL 合并异常。⟦/sys⟧",
            accumulator=think_acc,
        ):
            yield ev
        raise ValueError("未检索到可用文献结果，本次会话已终止。")

    if not merged and raw_total > 0 and merged_pre_corpus:
        merged = merged_pre_corpus
        async for ev in emit_system_think_line(
            f"⟦sys⟧合并后语料去重为 0，保留去重前 {len(merged)} 条用于抓取。⟦/sys⟧",
            accumulator=think_acc,
        ):
            yield ev

    out["hits"] = merged
    out["answer"] = answers[0] if answers else ""


async def stream_attributes_phase(
    *,
    user_message: str,
    corpus: SessionCorpus,
    fetch_results: list[tuple[dict[str, str], str, str | None]],
    cite_records: list[Any],
    llm,
    parallel: int,
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    result: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.skills.paper_attributes import (
        build_extraction_jobs,
        extract_attributes_batch,
        merge_paper_index,
        papers_needing_attributes,
    )

    out = result if result is not None else {}
    yield ("stage", {"name": "文献结构化", "state": "active"})

    jobs = build_extraction_jobs(
        fetch_results=fetch_results,
        cite_records=cite_records,
        paper_index=corpus.paper_index,
    )
    if not jobs:
        async for ev in emit_system_think_line(
            "文献结构化：无新增抓取材料或均已结构化。",
            accumulator=think_acc,
        ):
            yield ev
        yield ("stage", {"name": "文献结构化", "state": "done"})
        upsert_stage(execution_trace, "文献结构化", "done")
        out["paper_index"] = corpus.paper_index
        out["extracted"] = 0
        return

    async for ev in emit_system_think_line(
        f"正在结构化 {len(jobs)} 篇文献（AttributeTree lite）…",
        accumulator=think_acc,
    ):
        yield ev

    extracted = await extract_attributes_batch(llm, jobs, parallel=parallel)
    corpus.paper_index = merge_paper_index(corpus.paper_index, extracted)

    for rec in extracted:
        async for ev in emit_tool_event(
            lambda p, rid=rec.paper_id: f"{p}_{rid}",
            "extract_attributes",
            {"paper_id": rec.paper_id, "url": rec.url, "title": rec.title[:120]},
            str(rec.attri.get("problem") or rec.title)[:200],
            trace=execution_trace,
        ):
            yield ev

    attri_ctx = (
        f"【结构化文献】{len(corpus.paper_index)} 篇；"
        f"待补全 {papers_needing_attributes(corpus.paper_index)} 篇"
    )
    async for ev in narrate_phase_stream(
        "F2",
        user_message,
        attri_ctx,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        yield ev

    yield (
        "literature_paper_index",
        {
            "count": len(corpus.paper_index),
            "extracted": len(extracted),
            "sample_titles": [
                str(p.get("title") or "")[:80]
                for p in corpus.paper_index[:5]
            ],
        },
    )
    yield ("stage", {"name": "文献结构化", "state": "done"})
    upsert_stage(execution_trace, "文献结构化", "done")
    out["paper_index"] = corpus.paper_index
    out["extracted"] = len(extracted)


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
    fetch_throttle = (
        FetchNarrationThrottle()
        if should_narrate("D", planner_ctx)
        else None
    )
    recent_fetch_labels: list[str] = []

    async for hit, ctx_md, err in iter_fetch_sources_parallel(
        fetch_hits,
        api_key=fetch_api_key or None,
        llm=llm,
        parallel=parallel,
        timeout_per_url=timeout_sec,
        max_urls=fetch_cap,
        retry_count=fetch_retry_count,
        retry_delay_ms=fetch_retry_delay_ms,
        fetch_provider=fetch_provider,
    ):
        idx = fetch_idx
        fetch_idx += 1
        url = hit["url"]
        delta.fetch_results.append((hit, ctx_md or "", err))
        delta.fetch_hits.append(hit)
        delta.register_url(url)

        child_id = f"fetch_{idx}"
        child_meta = {
            "url": url,
            "title": hit.get("title") or "",
            "provider": fetch_provider,
        }
        async for ev in emitter.yield_begin(
            child_id, name="web_fetch", parent_id="fetch", metadata=child_meta
        ):
            yield ev

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
):
    from app.agents.literature_source import build_fetch_hits

    if user_urls and not hits:
        return build_fetch_hits(
            "user_only",
            [],
            user_urls,
            max_urls=fetch_cap,
        )
    return build_fetch_hits(source_mode, hits, user_urls, max_urls=fetch_cap)


def user_url_hits(urls: list[str]) -> list[dict[str, str]]:
    return hits_from_urls(urls)


OUTLINE_ARTIFACT_LANG = "literature-outline+json"


async def stream_outline_phase(
    *,
    user_message: str,
    search_query: str,
    session_title: str,
    session_id: str,
    corpus: SessionCorpus,
    store,
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    emitter,
    graph,
    graph_artifact_id: str,
    sync_graph_node,
    outline: Any | None = None,
    result: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.literature_outline import mount_papers_to_outline, prepare_outline
    from app.schemas.literature_outline import LiteratureOutline
    import json

    out = result if result is not None else {}
    yield ("stage", {"name": "大纲规划", "state": "active"})
    async for ev in sync_graph_node(
        emitter,
        graph,
        graph_artifact_id,
        "outline",
        "active",
        parent_id="attributes",
    ):
        yield ev

    if outline is None:
        outline = prepare_outline(
            user_message=user_message,
            search_query=search_query,
            session_title=session_title,
        )
    elif isinstance(outline, dict):
        outline = LiteratureOutline.from_dict(outline) or prepare_outline(
            user_message=user_message,
            search_query=search_query,
            session_title=session_title,
        )

    outline = mount_papers_to_outline(outline, corpus.paper_index)
    store.save_outline(session_id, outline.to_dict())

    async for ev in emit_system_think_line(
        f"大纲已生成：{len(outline.sections)} 个章节，"
        f"{len(outline.sub_topics)} 个子主题。",
        accumulator=think_acc,
    ):
        yield ev

    art_id = f"outline_{session_id[:8]}"
    yield (
        "artifact",
        {
            "id": art_id,
            "lang": OUTLINE_ARTIFACT_LANG,
            "delta": json.dumps(outline.to_dict(), ensure_ascii=False),
            "done": True,
        },
    )
    yield (
        "literature_outline",
        {
            "topic": outline.topic,
            "section_count": len(outline.sections),
            "sub_topic_count": len(outline.sub_topics),
            "sections": [
                {"id": s.id, "title": s.title, "papers": len(s.mounted_paper_ids)}
                for s in outline.sections
            ],
        },
    )

    async for ev in sync_graph_node(
        emitter,
        graph,
        graph_artifact_id,
        "outline",
        "done",
        parent_id="attributes",
    ):
        yield ev
    yield ("stage", {"name": "大纲规划", "state": "done"})
    upsert_stage(execution_trace, "大纲规划", "done")
    out["outline"] = outline

