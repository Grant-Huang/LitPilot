"""Retrieval pipeline: search → fetch → cite → attributes → outline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.agent_settings import is_plan_confirm_required
from app.agents.execution_trace import upsert_stage
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
    stream_search_phase,
    user_url_hits,
)
from app.agents.literature_planner import PlannerContext
from app.agents.literature_router import LiteratureRouterResult
from app.agents.literature_source import should_skip_tavily
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn, yield_clarification_pause
from app.agents.literature_turn_graph import sync_graph_node
from app.agents.literature_turn_helpers import augment_query, resolve_search_queries
from app.agents.search_expansion import expand_search_queries
from app.agents.session_corpus import SessionCorpus
from app.agents.url_list import effective_fetch_cap
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.schemas.literature_outline import LiteratureOutline
from app.services.llm_service import get_planner_llm


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
    llm: Any
    emitter: WorkflowNodeEmitter
    graph: Any
    graph_artifact_id: str
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    planner_ctx: PlannerContext
    citation_format: str
    fmt_label: str
    source_mode: str
    tavily_key: str | None
    tavily_max_results: int
    tavily_retry_count: int
    fetch_retry_delay_ms: int
    tavily_include_domains: list[str]
    tavily_exclude_domains: list[str]
    tavily_search_depth: str
    tavily_enforce_domain_filter: bool
    tavily_enable_junk_filter: bool
    enable_query_expansion: bool
    search_expansion_count: int
    enable_paper_attributes: bool
    max_fetch_urls: int
    max_source_chars: int
    jina_key: str | None
    parallel: int
    timeout_sec: int
    fetch_retry_count: int
    upload_urls: list[str]
    working: SessionCorpus
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
    early_return: bool = False


async def run_retrieval_pipeline(
    ctx: RetrievalPipelineContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    intent = ctx.intent
    working = ctx.working

    run_search = intent.intent in ("new_topic", "expand_search") or (
        intent.intent == "supplement" and not intent.skip_tavily
    ) or (intent.intent == "synthesis_matrix" and not intent.skip_tavily)
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
            yield ("text", {"delta": "没有可重试的失败链接。"})
            upsert_stage(ctx.execution_trace, "完成", "done")
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.fetch_results = []
            ctx.finalize_ctx.cite_records = []
            ctx.finalize_ctx.failed_literature = working.failed_literature
            ctx.finalize_ctx.intent = intent
            await finalize_turn(ctx.finalize_ctx, main_text="没有可重试的失败链接。")
            yield ("stage", {"name": "完成", "state": "done"})
            ctx.early_return = True
            return

    if run_search:
        base_query, query = resolve_search_queries(
            intent, ctx.router_result, ctx.route_message
        )
        skip_tavily = should_skip_tavily(ctx.source_mode, ctx.upload_urls)
        if intent.skip_tavily:
            skip_tavily = True
        search_out: dict[str, Any] = {}
        try:
            expanded_queries = [query]
            if (
                ctx.use_outline_path
                and len(ctx.sub_topics_for_search) >= 2
                and not skip_tavily
            ):
                expanded_queries = [
                    augment_query(str(st.search_query or query))
                    for st in ctx.sub_topics_for_search
                ]
            elif ctx.enable_query_expansion and ctx.search_expansion_count > 1:
                planner_llm = await get_planner_llm()
                expanded_queries = await expand_search_queries(
                    query,
                    count=ctx.search_expansion_count,
                    user_message=ctx.route_message,
                    llm=planner_llm,
                    use_llm=True,
                )

            if len(expanded_queries) > 1:
                async for ev in stream_expanded_search_phase(
                    user_message=ctx.route_message,
                    queries=expanded_queries,
                    tavily_key=ctx.tavily_key or "",
                    tavily_max_results=ctx.tavily_max_results,
                    tavily_retry_count=ctx.tavily_retry_count,
                    fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
                    source_mode=ctx.source_mode,
                    upload_count=len(ctx.upload_urls),
                    skip_tavily=skip_tavily,
                    upload_urls=ctx.upload_urls,
                    think_acc=ctx.think_acc,
                    planner_ctx=ctx.planner_ctx,
                    execution_trace=ctx.execution_trace,
                    corpus=working if ctx.turn_ctx.has_corpus else None,
                    result=search_out,
                    tavily_include_domains=ctx.tavily_include_domains,
                    tavily_exclude_domains=ctx.tavily_exclude_domains,
                    tavily_search_depth=ctx.tavily_search_depth,
                    tavily_enforce_domain_filter=ctx.tavily_enforce_domain_filter,
                    tavily_enable_junk_filter=ctx.tavily_enable_junk_filter,
                ):
                    yield ev
            else:
                async for ev in stream_search_phase(
                    user_message=ctx.route_message,
                    query=query,
                    tavily_key=ctx.tavily_key or "",
                    tavily_max_results=ctx.tavily_max_results,
                    tavily_retry_count=ctx.tavily_retry_count,
                    fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
                    source_mode=ctx.source_mode,
                    upload_count=len(ctx.upload_urls),
                    skip_tavily=skip_tavily,
                    upload_urls=ctx.upload_urls,
                    think_acc=ctx.think_acc,
                    planner_ctx=ctx.planner_ctx,
                    execution_trace=ctx.execution_trace,
                    corpus=working if ctx.turn_ctx.has_corpus else None,
                    result=search_out,
                    tavily_include_domains=ctx.tavily_include_domains,
                    tavily_exclude_domains=ctx.tavily_exclude_domains,
                    tavily_search_depth=ctx.tavily_search_depth,
                    tavily_enforce_domain_filter=ctx.tavily_enforce_domain_filter,
                    tavily_enable_junk_filter=ctx.tavily_enable_junk_filter,
                ):
                    yield ev
        except ValueError as e:
            fail_msg = str(e)
            yield ("text", {"delta": fail_msg})
            ctx.finalize_ctx.corpus = working
            ctx.finalize_ctx.fetch_results = []
            ctx.finalize_ctx.cite_records = []
            ctx.finalize_ctx.failed_literature = working.failed_literature
            ctx.finalize_ctx.intent = intent
            await finalize_turn(ctx.finalize_ctx, main_text=fail_msg)
            ctx.early_return = True
            return
        except Exception as e:
            if not ctx.upload_urls:
                fail_msg = f"Tavily 搜索不可用（{e}）。请检查 API Key；本次会话已终止。"
                yield ("text", {"delta": fail_msg})
                ctx.finalize_ctx.corpus = working
                ctx.finalize_ctx.fetch_results = []
                ctx.finalize_ctx.cite_records = []
                ctx.finalize_ctx.failed_literature = working.failed_literature
                ctx.finalize_ctx.intent = intent
                await finalize_turn(ctx.finalize_ctx, main_text=fail_msg)
                ctx.early_return = True
                return
            async for ev in emit_system_think_line(
                f"Tavily 检索失败，将仅使用用户链接（{len(ctx.upload_urls)} 条）。",
                accumulator=ctx.think_acc,
            ):
                yield ev

        ctx.hits = list(search_out.get("hits") or [])
        ctx.answer = str(search_out.get("answer") or "")

        search_zero_gate = detect_search_zero_gate(
            hits=ctx.hits,
            upload_urls=ctx.upload_urls,
            skip_tavily=skip_tavily,
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
            )
        else:
            build_result = build_fetch_queue(
                source_mode=ctx.source_mode,
                hits=ctx.hits,
                user_urls=ctx.upload_urls,
                fetch_cap=fetch_cap,
            )
        fetch_hits = [
            h
            for h in build_result.hits
            if not working.has_url(str(h.get("url") or ""))
        ]

        yield (
            "literature_source",
            {
                "mode": build_result.mode,
                "user_count": build_result.user_count,
                "tavily_count": build_result.tavily_count,
                "skipped_tavily": build_result.skipped_tavily or intent.skip_tavily,
                "total_fetch": len(fetch_hits),
            },
        )

        if fetch_hits:
            fetch_out: dict[str, Any] = {}
            async for ev in stream_fetch_phase(
                user_message=ctx.user_message,
                fetch_hits=fetch_hits,
                fetch_cap=fetch_cap,
                jina_key=ctx.jina_key,
                llm=ctx.llm,
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
                tavily_answer=ctx.answer,
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
                jina_key=ctx.jina_key,
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
                yield ("text", {"delta": msg})
                upsert_stage(ctx.execution_trace, "完成", "done")
                ctx.finalize_ctx.corpus = working
                ctx.finalize_ctx.fetch_results = []
                ctx.finalize_ctx.cite_records = []
                ctx.finalize_ctx.failed_literature = working.failed_literature
                ctx.finalize_ctx.intent = intent
                await finalize_turn(ctx.finalize_ctx, main_text=msg)
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
                "tavily_count": 0,
                "skipped_tavily": True,
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
                llm=ctx.llm,
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
