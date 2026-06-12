"""v2 per-subtopic retrieval: search → filter → fetch → cite → enrich."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

MAX_PARALLEL_SUBTOPICS = 3

from app.agents.enrich_lite import extract_enrich_lite_from_text
from app.agents.execution_trace import record_literature_stats, upsert_stage
from app.agents.intent_policy import runs_fetch, runs_search
from app.agents.literature_intent import (
    LiteratureIntentResult,
    build_append_urls_notice,
)
from app.agents.literature_phases import (
    stream_cite_phase,
    stream_fetch_phase,
    stream_search_phase,
    user_url_hits,
)
from app.agents.literature_router import LiteratureRouterResult
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn
from app.agents.literature_turn_graph import sync_graph_node, sync_graph_nodes
from app.agents.relevance_filter import (
    RelevanceFilterResult,
    _filter_subtopic_hits_stream,
)
from app.agents.search_aspects import collect_search_exclusions, sub_topic_pass_spec
from app.agents.search_query_refiner import refine_literature_search_queries
from app.agents.session_corpus import SessionCorpus
from app.agents.subtopic_tagging import tag_items_to_subtopics
from app.agents.url_list import canonical_url_keys
from app.core.stream_events import chat_text
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.library.canonical import canonical_key
from app.library.subtopic_tags import normalize_subtopic_id
from app.schemas.corpus_paper import CorpusPaperRecord, FETCH_STATUS_FAILED, FETCH_STATUS_OK
from app.schemas.literature_outline import LiteratureOutline, ResearchSubTopic
from app.services.llm_service import get_search_llm

_LEGACY_EXTENSIONS = frozenset(
    {
        "literature_search_plan",
        "literature_search_pass_start",
        "literature_search_pass_done",
        "literature_search_pass_hits",
        "literature_search_merge",
        "literature_fetch_start",
        "literature_fetch_user_start",
        "literature_outline",
        "literature_paper_index",
    }
)


@dataclass
class SubtopicPipelineContext:
    session_id: str
    user_message: str
    route_message: str
    session_title: str
    search_query_for_plan: str
    intent: LiteratureIntentResult
    router_result: LiteratureRouterResult
    finalize_ctx: TurnFinalizeContext
    store: Any
    pipeline_llm: Any
    emitter: Any
    graph: Any
    graph_artifact_id: str
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    planner_ctx: Any
    citation_format: str
    fmt_label: str
    search_api_key: str | None
    search_max_results: int
    search_retry_count: int
    fetch_retry_delay_ms: int
    search_include_domains: list[str]
    search_exclude_domains: list[str]
    search_depth: str
    search_enforce_domain_filter: bool
    search_enable_junk_filter: bool
    max_fetch_urls: int
    max_source_chars: int
    fetch_api_key: str | None
    parallel: int
    timeout_sec: int
    fetch_retry_count: int
    working: SessionCorpus
    outline: LiteratureOutline
    sub_topics: list[ResearchSubTopic]
    search_provider: str = "multi_academic"
    fetch_provider: str = "native"
    fetch_results: list[tuple[dict[str, str], str, str | None]] = field(
        default_factory=list
    )
    cite_records: list[Any] = field(default_factory=list)
    failed_literature: list[dict[str, str]] = field(default_factory=list)
    fetch_ok: int = 0
    fetch_failed: int = 0
    early_return: bool = False
    changed_subtopic_ids: list[str] = field(default_factory=list)


def _per_subtopic_cap(total_budget: int, n: int) -> int:
    if n <= 0:
        return total_budget
    return max(2, total_budget // n)


def _forward_event(ev: tuple[str, dict[str, Any]]) -> bool:
    name = ev[0]
    if name in _LEGACY_EXTENSIONS:
        return False
    if name == "extension" and (ev[1] or {}).get("name") in _LEGACY_EXTENSIONS:
        return False
    return True


async def _filter_subtopic_hits(
    *,
    hits: list[dict[str, str]],
    user_message: str,
    search_query: str,
    llm: Any,
    think_acc: Any = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Per-subtopic relevance filter; forwards ``think`` SSE to the caller.

    Yields ``("think", {...})`` chunks so the UI think fold updates while the
    relevance LLM streams reasoning/content. The terminal event is
    ``("filter_result", {"kept": [...]})`` carrying the kept hits.
    """
    if not hits:
        yield ("filter_result", {"kept": []})
        return
    result: RelevanceFilterResult | None = None
    async for ev in _filter_subtopic_hits_stream(
        hits=hits,
        user_message=user_message,
        search_query=search_query,
        llm=llm,
        think_acc=think_acc,
    ):
        if ev[0] == "_filter_done":
            result = ev[1]
            continue
        yield ev
    kept = list(result.kept_hits) if result is not None else []
    rejected = (
        [
            {"title": d.title, "url": d.url, "score": d.score, "reason": d.reason}
            for d in result.rejected
        ]
        if result is not None
        else []
    )
    yield ("filter_result", {"kept": kept, "rejected": rejected})


async def _run_subtopic(
    ctx: SubtopicPipelineContext,
    st: ResearchSubTopic,
    *,
    pass_index: int,
    pass_total: int,
    seen_url_keys: set[str],
    fetch_slots_left: int,
    corpus_base: SessionCorpus | None,
    seen_source_hits: set[str] | None = None,
    source_locks: dict[str, asyncio.Lock] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    subtopic_id = normalize_subtopic_id(st.id)
    query = str(st.search_query or ctx.search_query_for_plan)
    t0 = time.monotonic()

    _, source_queries, skip_sources = sub_topic_pass_spec(st)
    # Skip sources that already returned hits in earlier subtopics
    if seen_source_hits:
        skip_sources |= seen_source_hits
    per_cap = _per_subtopic_cap(ctx.search_max_results, pass_total)

    search_out: dict[str, Any] = {}
    async for ev in stream_search_phase(
        user_message=ctx.route_message,
        query=query,
        search_api_key=ctx.search_api_key or "",
        search_max_results=per_cap,
        search_retry_count=ctx.search_retry_count,
        fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
        source_mode="merge",
        upload_count=0,
        skip_web_search=False,
        upload_urls=[],
        think_acc=ctx.think_acc,
        planner_ctx=ctx.planner_ctx,
        execution_trace=ctx.execution_trace,
        corpus=corpus_base,
        result=search_out,
        search_include_domains=ctx.search_include_domains,
        search_exclude_domains=ctx.search_exclude_domains,
        search_depth=ctx.search_depth,
        search_enforce_domain_filter=ctx.search_enforce_domain_filter,
        search_enable_junk_filter=ctx.search_enable_junk_filter,
        exclude_title_substrings=collect_search_exclusions(
            ctx.router_result.search_aspects,
            extra=list(st.exclude_terms or []),
        ),
        pass_index=pass_index,
        pass_total=pass_total,
        topic_title=st.title,
        emit_stage_lifecycle=False,
        search_provider=ctx.search_provider,
        emit_pass_hits=False,
        source_queries=source_queries or None,
        skip_sources=skip_sources or None,
        source_locks=source_locks,
        seen_source_hits=seen_source_hits,
    ):
        if ev[0] == "literature_search_source_done":
            hits = int(ev[1].get("hits") or 0)
            source = str(ev[1].get("source") or "")
            if hits > 0 and source and seen_source_hits is not None:
                seen_source_hits.add(source)
        if _forward_event(ev):
            yield ev

    raw_hits = list(search_out.get("hits") or [])
    duration_ms = int((time.monotonic() - t0) * 1000)
    yield (
        "literature_subtopic_search_done",
        {
            "subtopic_id": subtopic_id,
            "title": st.title,
            "raw_count": len(raw_hits),
            "duration_ms": duration_ms,
        },
    )

    kept: list[dict[str, str]] = []
    rejected: list[dict[str, Any]] = []
    async for ev in _filter_subtopic_hits(
        hits=raw_hits,
        user_message=ctx.route_message,
        search_query=query,
        llm=ctx.pipeline_llm,
        think_acc=None,  # Don't pollute shared think accumulator with raw filter JSON
    ):
        if ev[0] == "filter_result":
            kept = list(ev[1].get("kept") or [])
            rejected = list(ev[1].get("rejected") or [])
            continue
        if ev[0] == "think":
            continue  # Filter LLM raw JSON decisions should not reach frontend
        yield ev

    deduped_kept: list[dict[str, str]] = []
    for hit in kept:
        url = str(hit.get("url") or "")
        key = canonical_key(url=url) or url
        if key and key in seen_url_keys:
            ctx.working.merge_papers(
                [
                    CorpusPaperRecord(
                        url=url,
                        title=str(hit.get("title") or ""),
                        subtopic_tags=[subtopic_id],
                    )
                ]
            )
            continue
        if key:
            seen_url_keys.add(key)
        hit = dict(hit)
        hit["subtopic_id"] = subtopic_id
        deduped_kept.append(hit)

    yield (
        "literature_subtopic_filter_done",
        {
            "subtopic_id": subtopic_id,
            "kept_count": len(deduped_kept),
            "kept_urls": [h.get("url") for h in deduped_kept if h.get("url")],
            "kept": [
                {"title": h.get("title", ""), "url": h.get("url", "")}
                for h in kept
                if h.get("title") or h.get("url")
            ],
            "rejected": rejected,
        },
    )

    if not deduped_kept or fetch_slots_left <= 0:
        yield (
            "literature_subtopic_fetch_done",
            {
                "subtopic_id": subtopic_id,
                "ok": 0,
                "failed": 0,
                "skipped": len(deduped_kept),
            },
        )
        return

    batch = deduped_kept[:fetch_slots_left]
    fetch_out: dict[str, Any] = {}
    _fetch_exc = None
    try:
        async for ev in stream_fetch_phase(
            user_message=ctx.user_message,
            fetch_hits=batch,
            fetch_cap=len(batch),
            fetch_api_key=ctx.fetch_api_key,
            fetch_provider=ctx.fetch_provider,
            llm=ctx.pipeline_llm,
            parallel=ctx.parallel,
            timeout_sec=ctx.timeout_sec,
            fetch_retry_count=ctx.fetch_retry_count,
            fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
            think_acc=ctx.think_acc,
            planner_ctx=ctx.planner_ctx,
            execution_trace=ctx.execution_trace,
            emitter=ctx.emitter,
            graph=ctx.graph,
            graph_artifact_id=ctx.graph_artifact_id,
            sync_graph_node=sync_graph_node,
            search_answer=str(search_out.get("answer") or ""),
            result=fetch_out,
            max_source_chars=ctx.max_source_chars,
        ):
            if _forward_event(ev):
                yield ev
    except Exception:
        _fetch_exc = True
        _log.exception(
            "subtopic %s fetch_phase raised; attempting partial merge",
            subtopic_id,
        )

    # 即使后续处理抛出异常，也先确保 fetch 获取的数据不丢失。
    # stream_fetch_phase 执行完成后，fetch_out["delta"] 已经被赋值。
    # try/finally 保护 merge 操作不受后续 paper 构建代码异常影响。
    fetch_delta: SessionCorpus = fetch_out.get("delta") or SessionCorpus()
    fetch_ok = int(fetch_out.get("fetch_ok") or 0)
    fetch_failed = int(fetch_out.get("fetch_failed") or 0)
    ctx.fetch_ok += fetch_ok
    ctx.fetch_failed += fetch_failed

    # 如果 fetch 完全没有产出数据（全部失败或未完成），但 batch 有应请求条目，
    # 将基础元数据写入 working，避免下游因 working.fetch_hits 为空而误判为"无可用文献"。
    if not fetch_delta.fetch_hits and not fetch_delta.sources_md and batch:
        for hit in batch:
            h = dict(hit) if not isinstance(hit, dict) else dict(hit)
            url = str(h.get("url") or "")
            key = canonical_key(url=url) or url
            if key and key in ctx.working.known_url_keys:
                continue
            ctx.working.fetch_hits.append(h)
            if key:
                ctx.working.known_url_keys.add(key)
        _log.warning(
            "subtopic %s fetch produced no data for %d items; fallback metadata added",
            subtopic_id, len(batch),
        )

    try:
        ctx.working.merge(fetch_delta)
        ctx.fetch_results.extend(fetch_delta.fetch_results)
        ctx.failed_literature.extend(fetch_delta.failed_literature)

        papers: list[CorpusPaperRecord] = []
        for hit, md, err in fetch_delta.fetch_results:
            url = str(hit.get("url") or "")
            status = FETCH_STATUS_OK if md and not err else FETCH_STATUS_FAILED
            lite = extract_enrich_lite_from_text(md or "")
            papers.append(
                CorpusPaperRecord(
                    url=url,
                    title=str(hit.get("title") or ""),
                    subtopic_tags=[subtopic_id],
                    fetch_status=status,
                    cite_in_review=status == FETCH_STATUS_OK,
                    enrich_lite=lite,
                )
            )
        ctx.working.merge_papers(papers)
    except Exception:
        _log.exception(
            "subtopic %s paper merge failed after fetch; fetch delta already merged",
            subtopic_id,
        )

    yield (
        "literature_subtopic_fetch_done",
        {
            "subtopic_id": subtopic_id,
            "ok": fetch_ok,
            "failed": fetch_failed,
            "skipped": max(0, len(deduped_kept) - len(batch)),
        },
    )


async def run_subtopic_retrieval(
    ctx: SubtopicPipelineContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    intent = ctx.intent
    working = ctx.working

    if intent.intent == "append_urls":
        async for ev in _run_append_urls(ctx):
            yield ev
        return

    if not runs_search(intent) and not runs_fetch(intent):
        if intent.intent in ("review_refine", "query_corpus"):
            async for ev in emit_system_think_line(
                f"复用已有语料（{working.source_block_count()} 个材料块）。",
                accumulator=ctx.think_acc,
            ):
                yield ev
            upsert_stage(ctx.execution_trace, "文献检索", "skipped")
            upsert_stage(ctx.execution_trace, "抓取网页", "skipped")
            upsert_stage(ctx.execution_trace, "引用抽取", "skipped")
            async for ev in sync_graph_nodes(
                ctx.emitter,
                ctx.graph,
                ctx.graph_artifact_id,
                ["fetch", "cite_extract"],
                "skipped",
            ):
                yield ev
            ctx.failed_literature = list(working.failed_literature)
            ctx.fetch_results = list(working.fetch_results)
        return

    subtopics = _subtopics_for_run(ctx)
    if not subtopics:
        msg = "未识别到子主题，请补充研究说明。"
        yield chat_text(msg)
        ctx.early_return = True
        ctx.finalize_ctx.chat_text = msg
        _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
        yield end_ev
        return

    yield (
        "literature_subtopic_plan",
        {
            "count": len(subtopics),
            "subtopics": [
                {
                    "id": st.id,
                    "title": st.title,
                    "search_query": st.search_query,
                }
                for st in subtopics
            ],
        },
    )

    search_llm = await get_search_llm()
    queries = [st.search_query for st in subtopics]
    refinement = await refine_literature_search_queries(
        queries,
        user_message=ctx.route_message,
        llm=search_llm,
        use_llm=True,
    )
    if refinement.queries:
        for st, q in zip(subtopics, refinement.queries):
            if q.strip():
                st.search_query = q.strip()

    corpus_base = working if working.known_url_keys else None
    seen_keys: set[str] = set(working.known_url_keys)
    seen_source_hits: set[str] = set()
    fetch_left = ctx.max_fetch_urls
    total_raw = 0
    total_kept = 0

    upsert_stage(ctx.execution_trace, "文献检索", "active")
    yield ("stage", {"name": "文献检索", "state": "active"})

    # 并行检索每个子主题：预分配抓取额度，sem 限并发避免冲击 API
    n = len(subtopics)
    per_st_fetch = max(2, ctx.max_fetch_urls // max(1, n))
    queue: asyncio.Queue = asyncio.Queue()
    sem = asyncio.Semaphore(min(MAX_PARALLEL_SUBTOPICS, n))
    source_locks: dict[str, asyncio.Lock] = {}

    async def _runner(idx: int, st: ResearchSubTopic) -> None:
        async with sem:
            try:
                async for ev in _run_subtopic(
                    ctx,
                    st,
                    pass_index=idx,
                    pass_total=n,
                    seen_url_keys=seen_keys,
                    fetch_slots_left=per_st_fetch,
                    corpus_base=corpus_base,
                    seen_source_hits=seen_source_hits,
                    source_locks=source_locks,
                ):
                    await queue.put(ev)
            except Exception as exc:
                await queue.put(("_subtopic_error", {"subtopic_id": st.id, "error": str(exc)}))
            finally:
                await queue.put(("_subtopic_done", {"subtopic_id": st.id}))

    tasks = [asyncio.create_task(_runner(i, st)) for i, st in enumerate(subtopics, start=1)]
    pending = n
    while pending > 0:
        ev = await queue.get()
        if ev[0] == "_subtopic_done":
            pending -= 1
            continue
        if ev[0] == "_subtopic_error":
            pending -= 1
            continue
        yield ev
        if ev[0] == "literature_subtopic_search_done":
            total_raw += int(ev[1].get("raw_count") or 0)
        if ev[0] == "literature_subtopic_filter_done":
            total_kept += int(ev[1].get("kept_count") or 0)
        if ev[0] == "literature_subtopic_fetch_done":
            fetch_left -= int(ev[1].get("ok") or 0) + int(ev[1].get("failed") or 0)
    # 保证所有任务结束
    for t in tasks:
        if not t.done():
            try:
                await t
            except Exception:
                pass

    upsert_stage(ctx.execution_trace, "文献检索", "done")
    yield ("stage", {"name": "文献检索", "state": "done"})
    record_literature_stats(
        ctx.execution_trace,
        searchMerged=total_kept,
    )

    if runs_search(intent):
        if total_kept == 0:
            msg = "本轮各子主题均未纳入文献。下轮可明确说明「增加/修改子主题」以调整检索。"
            yield chat_text(msg)
            ctx.early_return = True
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.chat_text = msg
            _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
            yield end_ev
            yield ("stage", {"name": "完成", "state": "done"})
            return
        if not working.fetch_hits and not working.sources_md:
            async for ev in emit_system_think_line(
                "检索到文献，但抓取网页时全部失败（可能为网络环境问题）。将继续尝试基于检索元数据生成。",
                accumulator=ctx.think_acc,
            ):
                yield ev

    if ctx.fetch_results:
        cite_out: dict[str, Any] = {}
        fetch_hits = [h for h, _, _ in ctx.fetch_results]
        async for ev in stream_cite_phase(
            user_message=ctx.user_message,
            fetch_hits=fetch_hits,
            fetch_cap=len(fetch_hits),
            fetch_api_key=ctx.fetch_api_key,
            timeout_sec=ctx.timeout_sec,
            citation_format=ctx.citation_format,
            fmt_label=ctx.fmt_label,
            session_id=ctx.session_id,
            session_title=ctx.session_title,
            think_acc=ctx.think_acc,
            planner_ctx=ctx.planner_ctx,
            execution_trace=ctx.execution_trace,
            emitter=ctx.emitter,
            graph=ctx.graph,
            graph_artifact_id=ctx.graph_artifact_id,
            sync_graph_node=sync_graph_node,
            store=ctx.store,
            failed_literature=ctx.failed_literature,
            result=cite_out,
        ):
            if _forward_event(ev):
                yield ev
        ctx.cite_records = list(cite_out.get("cite_records") or [])
        ref_text = str(cite_out.get("ref_text") or "")
        if ref_text.strip():
            block = f"## [Citations] 已收录引用\n\n{ref_text[-8000:]}\n"
            if block not in working.sources_md:
                working.sources_md.append(block)

    ctx.store.save_outline(ctx.session_id, ctx.outline.to_dict())
    ctx.working = working


def _subtopics_for_run(ctx: SubtopicPipelineContext) -> list[ResearchSubTopic]:
    if ctx.intent.intent == "subtopic_change" and ctx.changed_subtopic_ids:
        ids = set(ctx.changed_subtopic_ids)
        return [st for st in ctx.sub_topics if st.id in ids]
    return list(ctx.sub_topics)


async def _run_append_urls(
    ctx: SubtopicPipelineContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    urls = intent_urls = ctx.intent.new_urls
    if not urls:
        msg = build_append_urls_notice(updated_titles=[])
        yield chat_text(msg)
        ctx.early_return = True
        ctx.finalize_ctx.chat_text = msg
        _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
        yield end_ev
        return

    hits = user_url_hits(urls)
    fetch_out: dict[str, Any] = {}
    async for ev in stream_fetch_phase(
        user_message=ctx.user_message,
        fetch_hits=hits,
        fetch_cap=len(hits),
        fetch_api_key=ctx.fetch_api_key,
        fetch_provider=ctx.fetch_provider,
        llm=ctx.pipeline_llm,
        parallel=ctx.parallel,
        timeout_sec=ctx.timeout_sec,
        fetch_retry_count=ctx.fetch_retry_count,
        fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
        think_acc=ctx.think_acc,
        planner_ctx=ctx.planner_ctx,
        execution_trace=ctx.execution_trace,
        emitter=ctx.emitter,
        graph=ctx.graph,
        graph_artifact_id=ctx.graph_artifact_id,
        sync_graph_node=sync_graph_node,
        result=fetch_out,
        max_source_chars=ctx.max_source_chars,
    ):
        if _forward_event(ev):
            yield ev

    delta: SessionCorpus = fetch_out.get("delta") or SessionCorpus()
    ctx.working.merge(delta)
    ctx.fetch_results = list(delta.fetch_results)
    ctx.failed_literature = list(delta.failed_literature)
    ctx.fetch_ok = int(fetch_out.get("fetch_ok") or 0)
    ctx.fetch_failed = int(fetch_out.get("fetch_failed") or 0)

    cite_out: dict[str, Any] = {}
    if delta.fetch_results:
        async for ev in stream_cite_phase(
            user_message=ctx.user_message,
            fetch_hits=[h for h, _, _ in delta.fetch_results],
            fetch_cap=len(delta.fetch_results),
            fetch_api_key=ctx.fetch_api_key,
            timeout_sec=ctx.timeout_sec,
            citation_format=ctx.citation_format,
            fmt_label=ctx.fmt_label,
            session_id=ctx.session_id,
            session_title=ctx.session_title,
            think_acc=ctx.think_acc,
            planner_ctx=ctx.planner_ctx,
            execution_trace=ctx.execution_trace,
            emitter=ctx.emitter,
            graph=ctx.graph,
            graph_artifact_id=ctx.graph_artifact_id,
            sync_graph_node=sync_graph_node,
            store=ctx.store,
            failed_literature=ctx.failed_literature,
            result=cite_out,
        ):
            if _forward_event(ev):
                yield ev
        ctx.cite_records = list(cite_out.get("cite_records") or [])

    tag_items = [
        {
            "title": h.get("title"),
            "url": h.get("url"),
            "snippet": md[:400] if md else "",
        }
        for h, md, err in delta.fetch_results
    ]
    tag_matrix = await tag_items_to_subtopics(
        tag_items,
        ctx.sub_topics,
        llm=ctx.pipeline_llm,
    )
    papers: list[CorpusPaperRecord] = []
    titles: list[str] = []
    chapter_hints: list[str] = []
    for (hit, md, err), tags in zip(delta.fetch_results, tag_matrix):
        url = str(hit.get("url") or "")
        status = FETCH_STATUS_OK if md and not err else FETCH_STATUS_FAILED
        lite = extract_enrich_lite_from_text(md or "")
        papers.append(
            CorpusPaperRecord(
                url=url,
                title=str(hit.get("title") or ""),
                subtopic_tags=tags,
                fetch_status=status,
                cite_in_review=False,
                enrich_lite=lite,
            )
        )
        if hit.get("title"):
            titles.append(str(hit["title"]))
        for sid in tags:
            for sec in ctx.outline.sections:
                if sec.sub_topic_id == sid:
                    chapter_hints.append(f"第{sec.number}章 {sec.title}")
                    break
            else:
                for st in ctx.sub_topics:
                    if st.id == sid:
                        chapter_hints.append(st.title)
                        break
    ctx.working.merge_papers(papers)

    msg = build_append_urls_notice(
        updated_titles=titles,
        chapter_hints=list(dict.fromkeys(chapter_hints))[:5],
    )
    yield chat_text(msg)
    ctx.early_return = True
    ctx.finalize_ctx.corpus = ctx.working
    ctx.finalize_ctx.fetch_results = ctx.fetch_results
    ctx.finalize_ctx.cite_records = ctx.cite_records
    ctx.finalize_ctx.failed_literature = ctx.failed_literature
    ctx.finalize_ctx.intent = ctx.intent
    ctx.finalize_ctx.chat_text = msg
    _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
    yield end_ev
    yield ("stage", {"name": "完成", "state": "done"})
