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
from app.agents.tools.cached_tools import cached_tavily_search
from app.agents.tools.tavily_search import (
    ACADEMIC_SEARCH_DOMAINS,
    DEFAULT_EXCLUDE_DOMAINS,
    filter_tavily_hits,
    restrict_hits_to_domains,
    normalize_tavily_results,
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
    tavily_key: str,
    tavily_max_results: int,
    tavily_retry_count: int,
    fetch_retry_delay_ms: int,
    source_mode: str,
    upload_count: int,
    skip_tavily: bool,
    upload_urls: list[str],
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    corpus: SessionCorpus | None = None,
    result: dict[str, Any] | None = None,
    tavily_include_domains: tuple[str, ...] | None = None,
    tavily_exclude_domains: tuple[str, ...] | None = None,
    tavily_search_depth: str = "advanced",
    tavily_enforce_domain_filter: bool = True,
    tavily_enable_junk_filter: bool = True,
    pass_index: int = 1,
    pass_total: int = 1,
    emit_stage_lifecycle: bool = True,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    include_domains = tavily_include_domains or ACADEMIC_SEARCH_DOMAINS
    exclude_domains = tavily_exclude_domains or DEFAULT_EXCLUDE_DOMAINS
    search_depth = tavily_search_depth if tavily_search_depth in ("basic", "advanced") else "advanced"
    hits: list[dict[str, str]] = []
    answer = ""
    out = result if result is not None else {}

    if emit_stage_lifecycle and pass_index == 1:
        yield ("stage", {"name": "文献检索", "state": "active"})

    if skip_tavily:
        async for ev in emit_system_think_line(
            f"已跳过 Tavily 网络检索（用户列表 {upload_count} 条）。",
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
            tavily_max_results=tavily_max_results,
            upload_count=upload_count,
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
    elif pass_total > 1:
        async for ev in emit_system_think_line(
            f"⟦sys⟧第 {pass_index}/{pass_total} 轮检索：{query[:80]}⟦/sys⟧",
            accumulator=think_acc,
        ):
            yield ev

    try:

        async def _tavily_call() -> dict:
            return await cached_tavily_search(
                tavily_key,
                query,
                max_results=tavily_max_results,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )

        t0 = time.monotonic()
        raw_search = await retry_async(
            _tavily_call,
            max_retries=tavily_retry_count,
            delay_ms=fetch_retry_delay_ms,
        )
        search_ms = int((time.monotonic() - t0) * 1000)
        hits = normalize_tavily_results(raw_search)
        if tavily_enable_junk_filter:
            hits = filter_tavily_hits(hits)
        if tavily_enforce_domain_filter:
            hits = restrict_hits_to_domains(hits, include_domains=include_domains)
        answer = str(raw_search.get("answer") or "").strip()

        if corpus:
            hits = [h for h in hits if not corpus.has_url(str(h.get("url") or ""))]

        async for ev in emit_tool_event(
            lambda p: f"{p}_search",
            "web_search",
            {
                "query": query,
                "provider": "tavily",
                "pass_index": pass_index,
                "pass_total": pass_total,
            },
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
            raise
        async for ev in emit_system_think_line(
            f"Tavily 检索失败，将仅使用用户链接（{len(upload_urls)} 条）。",
            accumulator=think_acc,
        ):
            yield ev
    else:
        if not hits and not answer and not upload_urls:
            raise ValueError("未检索到可用文献结果，本次会话已终止。")

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
    out["hits"] = hits
    out["answer"] = answer


async def stream_expanded_search_phase(
    *,
    user_message: str,
    queries: list[str],
    tavily_key: str,
    tavily_max_results: int,
    tavily_retry_count: int,
    fetch_retry_delay_ms: int,
    source_mode: str,
    upload_count: int,
    skip_tavily: bool,
    upload_urls: list[str],
    think_acc: ThinkAccumulator,
    planner_ctx,
    execution_trace: dict[str, Any],
    corpus: SessionCorpus | None = None,
    result: dict[str, Any] | None = None,
    tavily_include_domains: tuple[str, ...] | None = None,
    tavily_exclude_domains: tuple[str, ...] | None = None,
    tavily_search_depth: str = "advanced",
    tavily_enforce_domain_filter: bool = True,
    tavily_enable_junk_filter: bool = True,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    from app.agents.search_merge import merge_search_hits

    out = result if result is not None else {}
    clean_queries = [q.strip() for q in queries if q and q.strip()]
    if not clean_queries:
        clean_queries = [""]
    total = len(clean_queries)
    per_query_max = max(2, tavily_max_results // total)
    hits_lists: list[list[dict[str, str]]] = []
    answers: list[str] = []
    raw_total = 0

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
            tavily_key=tavily_key,
            tavily_max_results=per_query_max,
            tavily_retry_count=tavily_retry_count,
            fetch_retry_delay_ms=fetch_retry_delay_ms,
            source_mode=source_mode,
            upload_count=upload_count if idx == 1 else 0,
            skip_tavily=skip_tavily,
            upload_urls=upload_urls if idx == 1 else [],
            think_acc=think_acc,
            planner_ctx=planner_ctx,
            execution_trace=execution_trace,
            corpus=corpus,
            result=pass_out,
            tavily_include_domains=tavily_include_domains,
            tavily_exclude_domains=tavily_exclude_domains,
            tavily_search_depth=tavily_search_depth,
            tavily_enforce_domain_filter=tavily_enforce_domain_filter,
            tavily_enable_junk_filter=tavily_enable_junk_filter,
            pass_index=idx,
            pass_total=total,
            emit_stage_lifecycle=idx == 1 or idx == total,
        ):
            yield ev
        pass_hits = list(pass_out.get("hits") or [])
        raw_total += len(pass_hits)
        hits_lists.append(pass_hits)
        ans = str(pass_out.get("answer") or "").strip()
        if ans:
            answers.append(ans)

    merged = merge_search_hits(hits_lists, max_results=tavily_max_results)
    if corpus:
        merged = [h for h in merged if not corpus.has_url(str(h.get("url") or ""))]

    yield (
        "literature_search_merge",
        {
            "raw_total": raw_total,
            "deduped": len(merged),
            "cap": tavily_max_results,
        },
    )

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
    jina_key: str | None,
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
    tavily_answer: str = "",
    result: dict[str, Any] | None = None,
    max_source_chars: int = MAX_SOURCE_CHARS,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    out = result if result is not None else {}
    delta = SessionCorpus()
    if tavily_answer:
        delta.append_tavily_answer(tavily_answer)

    yield ("stage", {"name": "抓取网页", "state": "active"})
    async for ev in emit_system_think_line(
        f"开始并行抓取 {len(fetch_hits)} 篇来源（上限 {fetch_cap}）。",
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
        url = hit["url"]
        delta.fetch_results.append((hit, ctx_md or "", err))
        delta.fetch_hits.append(hit)
        delta.register_url(url)

        child_id = f"fetch_{idx}"
        child_meta = {"url": url, "title": hit.get("title") or ""}
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
                {"url": url, "title": display_title, "char_count": char_count},
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
                {"url": url, "title": display_title},
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
    jina_key: str | None,
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
        jina_api_key=jina_key or None,
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
        f"大纲已确认：{len(outline.sections)} 个章节，"
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

