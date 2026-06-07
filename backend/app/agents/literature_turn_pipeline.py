"""Retrieval pipeline: search → fetch → cite → attributes → outline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.agent_settings import is_plan_confirm_required
from app.agents.execution_trace import record_literature_stats, upsert_stage
from app.agents.literature_clarification import (
    ClarificationState,
    build_outline_confirm_gate,
    detect_search_zero_gate,
)
from app.agents.literature_intent import LiteratureIntentResult
from app.agents.literature_phases import (
    build_fetch_queue,
    stream_attributes_phase,
    stream_cite_phase,
    stream_expanded_search_phase,
    stream_fetch_phase,
    stream_outline_phase,
    stream_relevance_filter_phase,
    stream_search_phase,
    user_url_hits,
)
from app.agents.literature_planner import PlannerContext
from app.agents.literature_router import LiteratureRouterResult
from app.agents.literature_source import should_skip_web_search
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn, yield_clarification_pause
from app.core.stream_events import chat_text
from app.agents.literature_turn_graph import sync_graph_node, sync_graph_nodes
from app.agents.literature_turn_helpers import resolve_search_queries
from app.agents.fetch_coordinator import FetchCoordinator
from app.agents.search_aspects import collect_search_exclusions, sub_topic_pass_spec
from app.agents.search_expansion import expand_search_queries
from app.agents.search_query_refiner import refine_literature_search_queries
from app.agents.session_corpus import SessionCorpus
from app.agents.url_list import effective_fetch_cap
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.schemas.literature_outline import LiteratureOutline
from app.services.llm_service import get_search_llm


@dataclass
class RetrievalPipelineContext:
    session_id: str
    user_message: str
    route_message: str
    session_title: str
    search_query_for_plan: str
    intent: LiteratureIntentResult
    router_result: LiteratureRouterResult
    turn_ctx: Any
    clar_state: ClarificationState
    finalize_ctx: TurnFinalizeContext
    store: Any
    planner_llm: Any
    pipeline_llm: Any
    emitter: WorkflowNodeEmitter
    graph: Any
    graph_artifact_id: str
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    planner_ctx: PlannerContext
    citation_format: str
    fmt_label: str
    source_mode: str
    search_api_key: str | None
    search_max_results: int
    search_retry_count: int
    fetch_retry_delay_ms: int
    search_include_domains: list[str]
    search_exclude_domains: list[str]
    search_depth: str
    search_enforce_domain_filter: bool
    search_enable_junk_filter: bool
    enable_query_expansion: bool
    search_expansion_count: int
    enable_paper_attributes: bool
    max_fetch_urls: int
    max_source_chars: int
    fetch_api_key: str | None
    parallel: int
    timeout_sec: int
    fetch_retry_count: int
    upload_urls: list[str]
    working: SessionCorpus
    search_provider: str = "native"
    fetch_provider: str = "native"
    fetch_results: list[tuple[dict[str, str], str, str | None]] = field(default_factory=list)
    cite_records: list[Any] = field(default_factory=list)
    failed_literature: list[dict[str, str]] = field(default_factory=list)
    hits: list[dict[str, str]] = field(default_factory=list)
    answer: str = ""
    fetch_ok: int = 0
    fetch_failed: int = 0
    use_outline_path: bool = False
    outline_draft: LiteratureOutline | None = None
    outline_obj: LiteratureOutline | None = None
    sub_topics_for_search: list[Any] = field(default_factory=list)
    search_hit_exclusions: list[str] = field(default_factory=list)
    search_parallel: int = 1
    search_degraded: bool = False
    fetch_coord_metrics: dict[str, Any] = field(default_factory=dict)
    pipelined_fetch_results: list[tuple[dict[str, str], str, str | None]] = field(
        default_factory=list
    )
    early_return: bool = False


def _search_phase_corpus(ctx: RetrievalPipelineContext) -> SessionCorpus | None:
    """检索去重语料：has_corpus 时用已持久化的会话 corpus，避免 working 为空导致去重不一致。"""
    if not ctx.turn_ctx.has_corpus:
        return None
    saved = ctx.finalize_ctx.corpus
    if saved and (
        saved.known_url_keys
        or saved.fetch_hits
        or saved.sources_md
    ):
        return saved
    if ctx.working.known_url_keys or ctx.working.fetch_hits:
        return ctx.working
    return None


async def run_retrieval_pipeline(
    ctx: RetrievalPipelineContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    intent = ctx.intent
    working = ctx.working

    run_search = intent.intent in ("new_topic", "expand_search") or (
        intent.intent == "supplement" and not intent.skip_web_search
    ) or (intent.intent == "synthesis_matrix" and not intent.skip_web_search)
    run_fetch = intent.intent in (
        "new_topic",
        "expand_search",
        "supplement",
        "retry_failed",
        "synthesis_matrix",
    ) and not intent.skip_fetch

    if intent.intent == "retry_failed":
        retry_urls = ctx.upload_urls or intent.new_urls
        if retry_urls:
            ctx.hits = user_url_hits(retry_urls)
            run_fetch = True
        else:
            msg = "没有可重试的失败链接。"
            yield chat_text(msg)
            upsert_stage(ctx.execution_trace, "完成", "done")
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.fetch_results = []
            ctx.finalize_ctx.cite_records = []
            ctx.finalize_ctx.failed_literature = working.failed_literature
            ctx.finalize_ctx.intent = intent
            ctx.finalize_ctx.chat_text = msg
            _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
            yield end_ev
            yield ("stage", {"name": "完成", "state": "done"})
            ctx.early_return = True
            return

    if run_search:
        base_query, query = resolve_search_queries(
            intent, ctx.router_result, ctx.route_message
        )
        skip_web_search = should_skip_web_search(ctx.source_mode, ctx.upload_urls)
        if intent.skip_web_search:
            skip_web_search = True
        search_out: dict[str, Any] = {}
        try:
            aspect_extra: list[str] = []
            for st in ctx.sub_topics_for_search:
                aspect_extra.extend(getattr(st, "exclude_terms", None) or [])
            ctx.search_hit_exclusions = collect_search_exclusions(
                ctx.router_result.search_aspects,
                extra=aspect_extra,
            )
            planned_aspects = bool(ctx.router_result.search_aspects) and all(
                a.primary_query() for a in ctx.router_result.search_aspects
            )

            expanded_queries = [query]
            if (
                ctx.use_outline_path
                and len(ctx.sub_topics_for_search) >= 2
                and not skip_web_search
            ):
                expanded_queries = [
                    str(st.search_query or query)
                    for st in ctx.sub_topics_for_search
                ]
            elif (
                ctx.enable_query_expansion
                and ctx.search_expansion_count > 1
                and not skip_web_search
                and not planned_aspects
            ):
                search_llm = await get_search_llm()
                expanded_queries = await expand_search_queries(
                    query,
                    count=ctx.search_expansion_count,
                    user_message=ctx.route_message,
                    llm=search_llm,
                    use_llm=True,
                )

            if not skip_web_search and expanded_queries and not planned_aspects:
                search_llm = await get_search_llm()
                refinement = await refine_literature_search_queries(
                    expanded_queries,
                    user_message=ctx.route_message,
                    llm=search_llm,
                    use_llm=True,
                )
                expanded_queries = refinement.queries or expanded_queries
                ctx.search_hit_exclusions = collect_search_exclusions(
                    ctx.router_result.search_aspects,
                    extra=aspect_extra + list(refinement.exclude_title_substrings),
                )
                if len(expanded_queries) == 1:
                    query = expanded_queries[0]

            topic_titles: list[str] | None = None
            if ctx.use_outline_path and len(ctx.sub_topics_for_search) >= 2:
                topic_titles = [
                    str(st.title or "").strip()
                    for st in ctx.sub_topics_for_search
                ]

            single_source_queries: dict[str, str] = {}
            single_skip_sources: frozenset[str] = frozenset()
            if ctx.sub_topics_for_search:
                _, single_source_queries, single_skip_sources = sub_topic_pass_spec(
                    ctx.sub_topics_for_search[0]
                )
            elif ctx.router_result.search_aspects:
                first_aspect = ctx.router_result.search_aspects[0]
                single_source_queries = first_aspect.source_queries()
                single_skip_sources = first_aspect.skip_sources()

            fetch_cap_early = effective_fetch_cap(ctx.max_fetch_urls, ctx.upload_urls)
            pipe_coord: FetchCoordinator | None = None
            if run_fetch and not skip_web_search:
                pipe_coord = FetchCoordinator(
                    fetch_api_key=ctx.fetch_api_key,
                    llm=ctx.pipeline_llm,
                    parallel=ctx.parallel,
                    timeout_sec=float(ctx.timeout_sec),
                    fetch_retry_count=ctx.fetch_retry_count,
                    fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
                    fetch_provider=ctx.fetch_provider,
                    fetch_cap=fetch_cap_early,
                    upload_urls=ctx.upload_urls if ctx.source_mode == "merge" else None,
                    corpus=_search_phase_corpus(ctx),
                )
                if ctx.upload_urls and ctx.source_mode == "merge":
                    user_started = pipe_coord.start_user_urls(ctx.upload_urls)
                    if user_started:
                        yield (
                            "literature_fetch_user_start",
                            {
                                "count": user_started,
                                "urls": ctx.upload_urls[:user_started],
                            },
                        )

            use_expanded = len(expanded_queries) > 1
            if use_expanded:
                search_stream = stream_expanded_search_phase(
                    user_message=ctx.route_message,
                    queries=expanded_queries,
                    search_api_key=ctx.search_api_key or "",
                    search_max_results=ctx.search_max_results,
                    search_retry_count=ctx.search_retry_count,
                    fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
                    source_mode=ctx.source_mode,
                    upload_count=len(ctx.upload_urls),
                    skip_web_search=skip_web_search,
                    upload_urls=ctx.upload_urls,
                    think_acc=ctx.think_acc,
                    planner_ctx=ctx.planner_ctx,
                    execution_trace=ctx.execution_trace,
                    corpus=_search_phase_corpus(ctx),
                    result=search_out,
                    search_include_domains=ctx.search_include_domains,
                    search_exclude_domains=ctx.search_exclude_domains,
                    search_depth=ctx.search_depth,
                    search_enforce_domain_filter=ctx.search_enforce_domain_filter,
                    search_enable_junk_filter=ctx.search_enable_junk_filter,
                    exclude_title_substrings=ctx.search_hit_exclusions,
                    search_provider=ctx.search_provider,
                    search_parallel=ctx.search_parallel,
                    topic_titles=topic_titles,
                    search_sub_topics=(
                        ctx.sub_topics_for_search
                        if planned_aspects and len(ctx.sub_topics_for_search) >= 2
                        else None
                    ),
                )
            else:
                search_stream = stream_search_phase(
                    user_message=ctx.route_message,
                    query=query,
                    search_api_key=ctx.search_api_key or "",
                    search_max_results=ctx.search_max_results,
                    search_retry_count=ctx.search_retry_count,
                    fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
                    source_mode=ctx.source_mode,
                    upload_count=len(ctx.upload_urls),
                    skip_web_search=skip_web_search,
                    upload_urls=ctx.upload_urls,
                    think_acc=ctx.think_acc,
                    planner_ctx=ctx.planner_ctx,
                    execution_trace=ctx.execution_trace,
                    corpus=_search_phase_corpus(ctx),
                    result=search_out,
                    search_include_domains=ctx.search_include_domains,
                    search_exclude_domains=ctx.search_exclude_domains,
                    search_depth=ctx.search_depth,
                    search_enforce_domain_filter=ctx.search_enforce_domain_filter,
                    search_enable_junk_filter=ctx.search_enable_junk_filter,
                    exclude_title_substrings=ctx.search_hit_exclusions,
                    search_provider=ctx.search_provider,
                    emit_pass_hits=pipe_coord is not None,
                    source_queries=single_source_queries or None,
                    skip_sources=single_skip_sources or None,
                )

            async for ev in search_stream:
                yield ev
            if pipe_coord:
                pipe_coord.mark_search_ended()
                coord_result = await pipe_coord.finalize()
                ctx.pipelined_fetch_results = coord_result.results
                ctx.fetch_coord_metrics = coord_result.metrics.to_dict()
        except ValueError as e:
            raw = str(e)
            if "allowed_domains and blocked_domains" in raw:
                fail_msg = (
                    "检索配置错误：不能同时启用 include_domains 与 exclude_domains。"
                    "请在 设置 → 管理员配置 → 能力 → web_search 中保留其一，或切换为 Tavily 检索。"
                )
            else:
                fail_msg = raw
            yield chat_text(fail_msg)
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.fetch_results = []
            ctx.finalize_ctx.cite_records = []
            ctx.finalize_ctx.failed_literature = working.failed_literature
            ctx.finalize_ctx.intent = intent
            ctx.finalize_ctx.chat_text = fail_msg
            _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=fail_msg)
            yield end_ev
            ctx.early_return = True
            return
        except Exception as e:
            from app.agents.tools.web_providers import search_provider_display

            search_label = search_provider_display(ctx.search_provider)
            if not ctx.upload_urls:
                fail_msg = f"{search_label} 检索不可用（{e}）。请检查能力绑定与凭据；本次会话已终止。"
                yield chat_text(fail_msg)
                ctx.finalize_ctx.corpus = working
                ctx.finalize_ctx.fetch_results = []
                ctx.finalize_ctx.cite_records = []
                ctx.finalize_ctx.failed_literature = working.failed_literature
                ctx.finalize_ctx.intent = intent
                ctx.finalize_ctx.chat_text = fail_msg
                _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=fail_msg)
                yield end_ev
                ctx.early_return = True
                return
            async for ev in emit_system_think_line(
                f"{search_label} 检索失败，将仅使用用户链接（{len(ctx.upload_urls)} 条）。",
                accumulator=ctx.think_acc,
            ):
                yield ev
            ctx.search_degraded = True

        ctx.hits = list(search_out.get("hits") or [])
        ctx.answer = str(search_out.get("answer") or "")

        if (
            run_search
            and ctx.hits
            and not skip_web_search
            and not intent.skip_web_search
        ):
            rel_out: dict[str, Any] = {}
            async for ev in stream_relevance_filter_phase(
                user_message=ctx.route_message,
                search_query=ctx.search_query_for_plan or query,
                hits=ctx.hits,
                llm=ctx.pipeline_llm,
                think_acc=ctx.think_acc,
                execution_trace=ctx.execution_trace,
                result=rel_out,
            ):
                yield ev
            filtered = rel_out.get("kept_hits")
            if isinstance(filtered, list):
                ctx.hits = [dict(h) for h in filtered if isinstance(h, dict)]

        search_zero_gate = detect_search_zero_gate(
            hits=ctx.hits,
            upload_urls=ctx.upload_urls,
            skip_web_search=skip_web_search,
            query=query,
            answer=ctx.answer,
            gate_resolved=ctx.clar_state.resolved,
        )
        if search_zero_gate:
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.fetch_results = []
            ctx.finalize_ctx.cite_records = []
            ctx.finalize_ctx.failed_literature = working.failed_literature
            async for ev in yield_clarification_pause(
                search_zero_gate,
                ctx.finalize_ctx,
                gate_resolved=ctx.clar_state.resolved,
            ):
                yield ev
            ctx.early_return = True
            return

    fetch_cap = effective_fetch_cap(ctx.max_fetch_urls, ctx.upload_urls)
    fetch_hits: list[dict[str, str]] = []

    if run_fetch:
        if ctx.upload_urls and not ctx.hits:
            build_result = build_fetch_queue(
                source_mode="user_only",
                hits=[],
                user_urls=ctx.upload_urls,
                fetch_cap=fetch_cap,
                skip_reason="search_failed" if ctx.search_degraded else None,
            )
        else:
            build_result = build_fetch_queue(
                source_mode=ctx.source_mode,
                hits=ctx.hits,
                user_urls=ctx.upload_urls,
                fetch_cap=fetch_cap,
                skip_reason="search_failed" if ctx.search_degraded else None,
            )
        fetch_hits = [
            h
            for h in build_result.hits
            if str(h.get("source") or "") == "upload"
            or not working.has_url(str(h.get("url") or ""))
        ]

        pre_fetched_urls = {
            str(h.get("url") or "")
            for h, md, err in ctx.pipelined_fetch_results
            if md and not err
        }
        if pre_fetched_urls:
            fetch_hits = [
                h for h in fetch_hits
                if str(h.get("url") or "") not in pre_fetched_urls
            ]

        yield (
            "literature_source",
            {
                "mode": build_result.mode,
                "user_count": build_result.user_count,
                "search_hit_count": build_result.search_hit_count,
                "skipped_web_search": build_result.skipped_web_search or intent.skip_web_search,
                "total_fetch": len(fetch_hits),
                "fetch_provider": ctx.fetch_provider,
                "fetch_cap": fetch_cap,
                "skip_reason": build_result.skip_reason,
                "fetch_metrics": ctx.fetch_coord_metrics or None,
            },
        )
        record_literature_stats(
            ctx.execution_trace,
            fetchQueueTotal=len(fetch_hits),
        )

        if fetch_hits or ctx.pipelined_fetch_results:
            fetch_out: dict[str, Any] = {}
            if ctx.pipelined_fetch_results:
                for hit, md, err in ctx.pipelined_fetch_results:
                    working.fetch_results.append((hit, md or "", err))
                    working.fetch_hits.append(hit)
                    working.register_url(str(hit.get("url") or ""))
                    if md and not err:
                        block = md[: ctx.max_source_chars]
                        if not block.lstrip().startswith("##"):
                            header = hit.get("title") or hit.get("url") or ""
                            block = f"## [网页材料] {header}\n\n{block}"
                        working.sources_md.append(block)
            async for ev in stream_fetch_phase(
                user_message=ctx.user_message,
                fetch_hits=fetch_hits,
                fetch_cap=fetch_cap,
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
                search_answer=ctx.answer,
                result=fetch_out,
                max_source_chars=ctx.max_source_chars,
            ):
                yield ev
            delta: SessionCorpus = fetch_out.get("delta") or SessionCorpus()
            ctx.fetch_ok = int(fetch_out.get("fetch_ok") or 0)
            ctx.fetch_failed = int(fetch_out.get("fetch_failed") or 0)
            working.merge(delta)
            ctx.fetch_results = list(delta.fetch_results)
            ctx.failed_literature = list(delta.failed_literature)

            cite_out: dict[str, Any] = {}
            ctx.failed_literature = list(working.failed_literature)
            async for ev in stream_cite_phase(
                user_message=ctx.user_message,
                fetch_hits=fetch_hits,
                fetch_cap=fetch_cap,
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
                yield ev
            ctx.cite_records = list(cite_out.get("cite_records") or [])
            ref_text = str(cite_out.get("ref_text") or "")
            if ref_text.strip():
                block = f"## [Citations] 已收录引用\n\n{ref_text[-8000:]}\n"
                if block not in working.sources_md:
                    working.sources_md.append(block)
        elif intent.intent in ("supplement", "retry_failed", "expand_search"):
            msg = "没有新的文献链接需要抓取（可能已全部在库中）。"
            async for ev in emit_system_think_line(msg, accumulator=ctx.think_acc):
                yield ev
            if intent.defer_generate:
                yield chat_text(msg)
                upsert_stage(ctx.execution_trace, "完成", "done")
                ctx.finalize_ctx.corpus = working
                ctx.finalize_ctx.fetch_results = []
                ctx.finalize_ctx.cite_records = []
                ctx.finalize_ctx.failed_literature = working.failed_literature
                ctx.finalize_ctx.intent = intent
                ctx.finalize_ctx.chat_text = msg
                _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=msg)
                yield end_ev
                yield ("stage", {"name": "完成", "state": "done"})
                ctx.early_return = True
                return
    elif intent.intent in (
        "refine_gen",
        "regen_only",
        "query_corpus",
        "synthesis_matrix",
    ):
        yield (
            "literature_source",
            {
                "mode": "corpus_reuse",
                "user_count": 0,
                "search_hit_count": 0,
                "skipped_web_search": True,
                "total_fetch": 0,
            },
        )
        async for ev in emit_system_think_line(
            f"复用已有语料（{working.source_block_count()} 个材料块），跳过检索与抓取。",
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

    if ctx.enable_paper_attributes and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        attr_fetch_results = list(ctx.fetch_results) or list(working.fetch_results)
        if attr_fetch_results or working.paper_index:
            if ctx.use_outline_path:
                async for ev in sync_graph_node(
                    ctx.emitter,
                    ctx.graph,
                    ctx.graph_artifact_id,
                    "attributes",
                    "active",
                    parent_id="cite_extract",
                ):
                    yield ev
            attr_out: dict[str, Any] = {}
            async for ev in stream_attributes_phase(
                user_message=ctx.user_message,
                corpus=working,
                fetch_results=attr_fetch_results,
                cite_records=ctx.cite_records,
                llm=ctx.pipeline_llm,
                parallel=ctx.parallel,
                think_acc=ctx.think_acc,
                planner_ctx=ctx.planner_ctx,
                execution_trace=ctx.execution_trace,
                result=attr_out,
            ):
                yield ev
            if ctx.use_outline_path:
                async for ev in sync_graph_node(
                    ctx.emitter,
                    ctx.graph,
                    ctx.graph_artifact_id,
                    "attributes",
                    "done",
                    parent_id="cite_extract",
                ):
                    yield ev
    elif ctx.use_outline_path and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        async for ev in sync_graph_node(
            ctx.emitter,
            ctx.graph,
            ctx.graph_artifact_id,
            "attributes",
            "skipped",
            parent_id="cite_extract",
        ):
            yield ev

    if ctx.use_outline_path and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        if working.sources_md or working.fetch_hits:
            outline_out: dict[str, Any] = {}
            async for ev in stream_outline_phase(
                user_message=ctx.route_message,
                search_query=ctx.search_query_for_plan,
                session_title=ctx.session_title,
                session_id=ctx.session_id,
                corpus=working,
                store=ctx.store,
                think_acc=ctx.think_acc,
                planner_ctx=ctx.planner_ctx,
                execution_trace=ctx.execution_trace,
                emitter=ctx.emitter,
                graph=ctx.graph,
                graph_artifact_id=ctx.graph_artifact_id,
                sync_graph_node=sync_graph_node,
                outline=ctx.outline_draft,
                result=outline_out,
            ):
                yield ev
            ctx.outline_obj = outline_out.get("outline")
            if isinstance(ctx.outline_obj, LiteratureOutline):
                ctx.outline_draft = ctx.outline_obj

            plan_confirm = await is_plan_confirm_required()
            if (
                plan_confirm
                and ctx.outline_obj
                and not ctx.clar_state.resolved.get("outline_confirm")
            ):
                outline_gate = build_outline_confirm_gate(ctx.outline_obj)
                ctx.finalize_ctx.corpus = working
                ctx.finalize_ctx.fetch_results = ctx.fetch_results
                ctx.finalize_ctx.cite_records = ctx.cite_records
                ctx.finalize_ctx.failed_literature = ctx.failed_literature
                async for ev in yield_clarification_pause(
                    outline_gate,
                    ctx.finalize_ctx,
                    gate_resolved=ctx.clar_state.resolved,
                    resume_mode="generate_only",
                ):
                    yield ev
                ctx.early_return = True
                return

    ctx.working = working
