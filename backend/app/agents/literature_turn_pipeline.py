"""v2 retrieval entry — delegates to per-subtopic pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.literature_intent import LiteratureIntentResult
from app.agents.literature_router import LiteratureRouterResult
from app.agents.literature_subtopic_pipeline import (
    SubtopicPipelineContext,
    run_subtopic_retrieval,
)
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_planner import PlannerContext
from app.agents.session_corpus import SessionCorpus
from app.core.think_stream import ThinkAccumulator
from app.schemas.literature_outline import LiteratureOutline, ResearchSubTopic


@dataclass
class RetrievalPipelineContext:
    """Adapter context for literature_turn → subtopic pipeline."""

    session_id: str
    user_message: str
    route_message: str
    session_title: str
    search_query_for_plan: str
    intent: LiteratureIntentResult
    router_result: LiteratureRouterResult
    turn_ctx: Any
    finalize_ctx: TurnFinalizeContext
    store: Any
    pipeline_llm: Any
    emitter: Any
    graph: Any
    graph_artifact_id: str
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    planner_ctx: PlannerContext
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
    outline_obj: LiteratureOutline | None = None
    sub_topics_for_search: list[ResearchSubTopic] = field(default_factory=list)
    search_provider: str = "multi_academic"
    fetch_provider: str = "native"
    fetch_results: list[tuple[dict[str, str], str, str | None]] = field(default_factory=list)
    cite_records: list[Any] = field(default_factory=list)
    failed_literature: list[dict[str, str]] = field(default_factory=list)
    fetch_ok: int = 0
    fetch_failed: int = 0
    early_return: bool = False

    # Removed v1 fields (ignored if passed): clar_state, source_mode, enable_query_expansion, etc.


def _to_subtopic_ctx(ctx: RetrievalPipelineContext) -> SubtopicPipelineContext:
    outline = ctx.outline_obj
    if outline is None:
        from app.agents.literature_outline import build_subtopic_plan

        outline, _ = build_subtopic_plan(
            user_message=ctx.route_message,
            search_query=ctx.search_query_for_plan,
            session_title=ctx.session_title,
            search_aspects=ctx.router_result.search_aspects,
        )
    sub_topics = ctx.sub_topics_for_search or list(outline.sub_topics)
    changed: list[str] = []
    if ctx.intent.intent == "subtopic_change":
        existing_ids: set[str] = {
            str(tag)
            for p in ctx.working.papers
            for tag in (p.get("subtopic_tags") or [])
            if tag
        }
        changed = [st.id for st in sub_topics if st.id not in existing_ids]
        if not changed:
            changed = [st.id for st in sub_topics]
    return SubtopicPipelineContext(
        session_id=ctx.session_id,
        user_message=ctx.user_message,
        route_message=ctx.route_message,
        session_title=ctx.session_title,
        search_query_for_plan=ctx.search_query_for_plan,
        intent=ctx.intent,
        router_result=ctx.router_result,
        finalize_ctx=ctx.finalize_ctx,
        store=ctx.store,
        pipeline_llm=ctx.pipeline_llm,
        emitter=ctx.emitter,
        graph=ctx.graph,
        graph_artifact_id=ctx.graph_artifact_id,
        execution_trace=ctx.execution_trace,
        think_acc=ctx.think_acc,
        planner_ctx=ctx.planner_ctx,
        citation_format=ctx.citation_format,
        fmt_label=ctx.fmt_label,
        search_api_key=ctx.search_api_key,
        search_max_results=ctx.search_max_results,
        search_retry_count=ctx.search_retry_count,
        fetch_retry_delay_ms=ctx.fetch_retry_delay_ms,
        search_include_domains=ctx.search_include_domains,
        search_exclude_domains=ctx.search_exclude_domains,
        search_depth=ctx.search_depth,
        search_enforce_domain_filter=ctx.search_enforce_domain_filter,
        search_enable_junk_filter=ctx.search_enable_junk_filter,
        max_fetch_urls=ctx.max_fetch_urls,
        max_source_chars=ctx.max_source_chars,
        fetch_api_key=ctx.fetch_api_key,
        parallel=ctx.parallel,
        timeout_sec=ctx.timeout_sec,
        fetch_retry_count=ctx.fetch_retry_count,
        working=ctx.working,
        outline=outline,
        sub_topics=sub_topics,
        search_provider=ctx.search_provider,
        fetch_provider=ctx.fetch_provider,
        fetch_results=ctx.fetch_results,
        cite_records=ctx.cite_records,
        failed_literature=ctx.failed_literature,
        fetch_ok=ctx.fetch_ok,
        fetch_failed=ctx.fetch_failed,
        changed_subtopic_ids=changed,
    )


async def run_retrieval_pipeline(
    ctx: RetrievalPipelineContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    sub = _to_subtopic_ctx(ctx)
    async for ev in run_subtopic_retrieval(sub):
        yield ev
    ctx.working = sub.working
    import json, os as _os; _lf = _os.path.join(_os.path.dirname(__file__), "../../.cursor/debug-248692.log"); open(_lf, "a").write(json.dumps({"sessionId":"248692","location":"literature_turn_pipeline.py:151","message":"retrieval pipeline end","data":{"sources_md":len(ctx.working.sources_md),"fetch_hits":len(ctx.working.fetch_hits),"fetch_results":len(ctx.fetch_results),"papers":len(ctx.working.papers),"fetch_ok":ctx.fetch_ok,"fetch_failed":ctx.fetch_failed,"working_id":id(ctx.working)},"timestamp":__import__("time").time()*1000,"runId":"debug1","hypothesisId":"B"})+"\n")
    ctx.fetch_results = sub.fetch_results
    ctx.cite_records = sub.cite_records
    ctx.failed_literature = sub.failed_literature
    ctx.fetch_ok = sub.fetch_ok
    ctx.fetch_failed = sub.fetch_failed
    ctx.outline_obj = sub.outline
    ctx.early_return = sub.early_return
