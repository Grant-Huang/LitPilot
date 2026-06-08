"""Multi-turn literature session orchestration (v2)."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.agents.agent_settings import (
    get_citation_format,
    get_fetch_api_key,
    get_fetch_parallel,
    get_fetch_retry_count,
    get_fetch_retry_delay_ms,
    get_fetch_timeout_sec,
    get_max_fetch_urls,
    get_max_source_chars,
    get_search_depth,
    get_search_enable_junk_filter,
    get_search_enforce_domain_filter,
    get_search_exclude_domains,
    get_search_include_domains,
    get_search_max_results,
    get_search_retry_count,
    get_web_fetch_provider,
    get_web_search_api_key,
    get_web_search_provider,
)
from app.agents.agent_skills import skill_active_event
from app.agents.execution_trace import new_trace, upsert_stage
from app.agents.first_turn_assessor import (
    brief_assessment_from_router,
    format_brief_assessment_message,
)
from app.agents.intent_policy import runs_generate
from app.agents.literature_intent import (
    LiteratureIntentResult,
    build_session_turn_context,
    merge_gen_constraints,
    route_literature_intent,
)
from app.agents.literature_outline import build_subtopic_plan, mount_papers_by_subtopic_tags
from app.agents.literature_planner import load_planner_context, stream_understanding_and_route
from app.agents.literature_progress import literature_progress_payload
from app.agents.literature_router import (
    LiteratureRouterResult,
    resolve_auto_session_title,
    should_auto_rename_session,
)
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn
from app.agents.literature_turn_generate import GenerateTurnContext, stream_generate_turn
from app.agents.literature_turn_graph import publish_workflow_graph as _publish_workflow_graph
from app.agents.literature_turn_helpers import (
    intent_needs_web_search as _intent_needs_web_search,
    last_assistant_failed as _last_assistant_failed,
    new_id as _new_id,
    section_specs_for_graph as _section_specs_for_graph,
)
from app.agents.literature_turn_pipeline import RetrievalPipelineContext, run_retrieval_pipeline
from app.agents.review_prompt import citation_format_label
from app.agents.search_aspects import search_aspects_plan_ready
from app.agents.session_corpus import SessionCorpus, resolve_session_corpus
from app.agents.url_list import sanitize_fetch_urls
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.agents.workflow_graph import apply_fetch_provider_label, build_literature_graph
from app.core.stream_events import (
    chat_text,
    literature_brief_assessment,
    literature_phase_think,
    process_text,
    process_text_extension,
    turn_start,
)
from app.core.think_stream import ThinkAccumulator
from app.schemas.literature_outline import LiteratureOutline
from app.services.llm_service import get_pipeline_llm, get_planner_llm, get_review_llm
from app.storage.file_store import get_store

_log = logging.getLogger(__name__)


async def stream_literature_turn(
    session_id: str,
    user_message: str,
    *,
    extra_fetch_urls: list[str] | None = None,
    persist_user_message: bool = True,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    store = get_store()
    if persist_user_message:
        store.append_message(session_id, "user", user_message)

    # I/O 阶段进度提示，避免前端无反馈
    yield (
        "literature_progress",
        literature_progress_payload("understand", "正在加载会话数据…"),
    )

    # 将独立 Turso/DB 读操作并行化
    import asyncio

    citation_task = asyncio.ensure_future(get_citation_format())
    session_task = asyncio.to_thread(store.get_session, session_id)
    msgs_task = asyncio.to_thread(lambda: store.load_messages(session_id, limit=50))
    review_task = asyncio.to_thread(store.get_latest_review, session_id)
    corpus_task = asyncio.to_thread(resolve_session_corpus, store, session_id)

    session_meta, msgs, has_review, corpus = await asyncio.gather(
        session_task, msgs_task, review_task, corpus_task,
    )
    citation_format = await citation_task
    fmt_label = citation_format_label(citation_format)
    yield skill_active_event("literature-review")

    session_meta = session_meta or {}
    corpus = corpus or SessionCorpus()
    user_turns = sum(1 for m in msgs if m.get("role") == "user")
    last_failed = _last_assistant_failed(msgs)
    has_review = bool(has_review)

    turn_ctx = build_session_turn_context(
        session_id=session_id,
        session_meta=session_meta,
        user_turns=user_turns,
        corpus=corpus if (corpus.fetch_hits or corpus.sources_md) else None,
        last_failed=last_failed,
        has_review=has_review,
    )

    route_message = user_message
    think_acc = ThinkAccumulator()
    yield turn_start(turn_index=user_turns, intent="new_topic")
    # 前置 I/O 完成后立即告知前端当前阶段，避免长时间显示"正在连接…"
    yield (
        "literature_progress",
        literature_progress_payload("understand", "正在分析意图…"),
    )
    intent = await route_literature_intent(
        route_message,
        turn_ctx=turn_ctx,
        extra_urls=extra_fetch_urls,
        corpus=corpus if turn_ctx.has_corpus else None,
        last_failed=last_failed,
    )

    search_provider = await get_web_search_provider()
    if _intent_needs_web_search(intent) and search_provider not in (
        "openalex",
        "native",
        "multi_academic",
    ):
        if not await get_web_search_api_key():
            from app.agents.tools.web_providers import search_provider_display

            yield (
                "error",
                {"message": f"请先在设置页配置 {search_provider_display(search_provider)} API Key"},
            )
            return

    yield (
        "literature_intent",
        {
            "intent": intent.intent,
            "defer_generate": intent.defer_generate,
            "skip_web_search": intent.skip_web_search,
            "skip_fetch": intent.skip_fetch,
            "use_existing_corpus": intent.use_existing_corpus,
        },
    )

    graph_artifact_id = _new_id("wf")
    emitter = WorkflowNodeEmitter(graph_artifact_id)
    fetch_provider = await get_web_fetch_provider()
    execution_trace = new_trace()
    planner_ctx = await load_planner_context()
    working = SessionCorpus()
    if turn_ctx.has_corpus:
        working = SessionCorpus.from_dict(corpus.to_dict()) or working

    review_llm = await get_review_llm()
    pipeline_llm = await get_pipeline_llm()
    router_result = LiteratureRouterResult(session_title="", search_query="")
    outline_obj: LiteratureOutline | None = LiteratureOutline.from_dict(
        store.load_outline(session_id)
    )
    sub_topics: list[Any] = []
    search_query_for_plan = route_message.strip()
    session_title = str(session_meta.get("title") or "")
    initial_query = str(session_meta.get("initial_query") or route_message.strip())

    gen_constraints = merge_gen_constraints(
        list(session_meta.get("gen_constraints") or []),
        intent.gen_directives if intent.intent == "review_refine" else "",
    )

    finalize_ctx = TurnFinalizeContext(
        store=store,
        session_id=session_id,
        session_meta=session_meta,
        session_title=session_title,
        intent=intent,
        user_message=user_message,
        corpus=corpus,
        execution_trace=execution_trace,
        think_acc=think_acc,
        fetch_results=[],
        cite_records=[],
        failed_literature=[],
        gen_constraints=gen_constraints,
        turn_index=user_turns,
    )

    if intent.intent == "short_answer":
        yield ("stage", {"name": "理解研究问题", "state": "done"})
        msg = (
            "如需调整文献综述，请明确说明操作，例如：\n"
            "• 「增加子主题：XXX」—— 新增检索方向与章节\n"
            "• 「修改子主题 N 为 XXX」—— 替换现有章节\n"
            "• 「重写第 N 章 …」—— 只修改综述表述\n"
            "• 「我的文献库里有 … 吗？」—— 查询已有文献"
        )
        yield chat_text(msg)
        finalize_ctx.chat_text = msg
        _, end_ev = await finalize_turn(finalize_ctx, main_text=msg)
        yield end_ev
        return

    needs_understanding = intent.intent in ("new_topic", "subtopic_change", "append_urls")
    if needs_understanding:
        async for ev in stream_understanding_and_route(
            route_message,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            if ev[0] == "__router_result__":
                router_result = ev[1]["result"]
            else:
                yield ev
        planner_ctx.narration_focus = router_result.narration_focus
        planner_ctx.writing_emphasis = router_result.writing_emphasis

        if should_auto_rename_session(session_meta, route_message, user_message_count=user_turns):
            new_title = await resolve_auto_session_title(
                primary_title=router_result.session_title or "",
                user_message=route_message,
            )
            if new_title:
                store.update_session(session_id, title=new_title, title_auto_set=True)
                session_meta = store.get_session(session_id) or session_meta
                session_title = new_title
                yield ("session_title", {"session_id": session_id, "title": new_title})

        yield ("stage", {"name": "理解研究问题", "state": "done"})
        upsert_stage(execution_trace, "理解研究问题", "done")

        understand_think = think_acc.finalize()
        if understand_think:
            yield literature_phase_think("understand", understand_think)

        search_query_for_plan = (
            router_result.search_query.strip()
            or route_message.strip()
        )
        if search_aspects_plan_ready(router_result.search_aspects):
            brief = brief_assessment_from_router(router_result)
            rq_msg = format_brief_assessment_message(brief)
            if rq_msg:
                finalize_ctx.assistant_prefix = rq_msg
                finalize_ctx.process_text = rq_msg
                yield literature_brief_assessment(brief.to_dict())
                for para in rq_msg.split("\n\n"):
                    if para.strip():
                        chunk = para.strip() + "\n\n"
                        yield process_text(chunk)
                        yield process_text_extension(chunk)

        outline_obj, sub_topics = build_subtopic_plan(
            user_message=route_message,
            search_query=search_query_for_plan,
            session_title=session_title,
            search_aspects=router_result.search_aspects,
            stored_outline=outline_obj,
            intent=intent.intent,
        )
    else:
        yield ("stage", {"name": "理解研究问题", "state": "done"})
        upsert_stage(execution_trace, "理解研究问题", "done")

    g = build_literature_graph(
        _section_specs_for_graph(outline_obj) if outline_obj else None
    )
    apply_fetch_provider_label(g, fetch_provider)
    async for ev in _publish_workflow_graph(g, graph_artifact_id):
        yield ev

    upload_urls = sanitize_fetch_urls(extra_fetch_urls)
    if intent.new_urls:
        upload_urls = sanitize_fetch_urls(intent.new_urls + upload_urls)

    pipe_ctx = RetrievalPipelineContext(
        session_id=session_id,
        user_message=user_message,
        route_message=route_message,
        session_title=session_title,
        search_query_for_plan=search_query_for_plan,
        intent=intent,
        router_result=router_result,
        turn_ctx=turn_ctx,
        finalize_ctx=finalize_ctx,
        store=store,
        pipeline_llm=pipeline_llm,
        emitter=emitter,
        graph=g,
        graph_artifact_id=graph_artifact_id,
        execution_trace=execution_trace,
        think_acc=think_acc,
        planner_ctx=planner_ctx,
        citation_format=citation_format,
        fmt_label=fmt_label,
        search_api_key=await get_web_search_api_key(),
        search_max_results=await get_search_max_results(),
        search_retry_count=await get_search_retry_count(),
        fetch_retry_delay_ms=await get_fetch_retry_delay_ms(),
        search_include_domains=await get_search_include_domains(),
        search_exclude_domains=await get_search_exclude_domains(),
        search_depth=await get_search_depth(),
        search_enforce_domain_filter=await get_search_enforce_domain_filter(),
        search_enable_junk_filter=await get_search_enable_junk_filter(),
        max_fetch_urls=await get_max_fetch_urls(),
        max_source_chars=await get_max_source_chars(),
        fetch_api_key=await get_fetch_api_key(),
        parallel=await get_fetch_parallel(),
        timeout_sec=await get_fetch_timeout_sec(),
        fetch_retry_count=await get_fetch_retry_count(),
        working=working,
        outline_obj=outline_obj,
        sub_topics_for_search=sub_topics,
        search_provider=search_provider,
        fetch_provider=fetch_provider,
    )
    async for ev in run_retrieval_pipeline(pipe_ctx):
        yield ev
    if pipe_ctx.early_return:
        return

    working = pipe_ctx.working
    outline_obj = pipe_ctx.outline_obj or outline_obj

    if intent.intent == "query_corpus":
        if not working.sources_md and not working.fetch_hits:
            fail_msg = "当前会话尚无文献材料，无法回答。"
            yield chat_text(fail_msg)
            finalize_ctx.chat_text = fail_msg
            _, end_ev = await finalize_turn(finalize_ctx, main_text=fail_msg)
            yield end_ev
            return

    if not runs_generate(intent):
        return

    if not working.sources_md and not working.fetch_hits:
        fail_msg = "没有可用的文献材料。"
        yield chat_text(fail_msg)
        finalize_ctx.chat_text = fail_msg
        _, end_ev = await finalize_turn(finalize_ctx, main_text=fail_msg)
        yield end_ev
        return

    if outline_obj:
        outline_obj = mount_papers_by_subtopic_tags(outline_obj, working.papers)
        store.save_outline(session_id, outline_obj.to_dict())

    gen_ctx = GenerateTurnContext(
        session_id=session_id,
        user_message=user_message,
        route_message=route_message,
        initial_query=initial_query,
        session_title=session_title,
        intent=intent,
        gen_constraints=gen_constraints,
        citation_format=citation_format,
        fmt_label=fmt_label,
        finalize_ctx=finalize_ctx,
        store=store,
        llm=review_llm,
        emitter=emitter,
        graph=g,
        graph_artifact_id=graph_artifact_id,
        execution_trace=execution_trace,
        think_acc=think_acc,
        planner_ctx=planner_ctx,
        working=working,
        fetch_results=pipe_ctx.fetch_results,
        cite_records=pipe_ctx.cite_records,
        failed_literature=pipe_ctx.failed_literature,
        fetch_ok=pipe_ctx.fetch_ok,
        fetch_failed=pipe_ctx.fetch_failed,
        outline_obj=outline_obj,
    )
    async for ev in stream_generate_turn(gen_ctx):
        yield ev
