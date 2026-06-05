"""Multi-turn literature session orchestration."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.agents.agent_settings import (
    get_citation_format,
    get_enable_paper_attributes,
    get_enable_query_expansion,
    get_fetch_parallel,
    get_fetch_retry_count,
    get_fetch_retry_delay_ms,
    get_fetch_timeout_sec,
    get_fetch_api_key,
    get_literature_source_mode,
    get_max_fetch_urls,
    get_max_source_chars,
    get_outline_mode,
    get_post_refine_mode,
    get_search_expansion_count,
    get_web_search_api_key,
    get_web_search_provider,
    get_search_enable_junk_filter,
    get_search_enforce_domain_filter,
    get_search_exclude_domains,
    get_search_include_domains,
    get_search_max_results,
    get_search_retry_count,
    get_search_depth,
    get_web_fetch_provider,
)
from app.agents.agent_skills import skill_active_event
from app.agents.literature_clarification import (
    ClarificationGate,
    ClarificationState,
    assess_first_turn_gate,
    merge_first_turn_message,
    resolve_pending_gate,
)
from app.agents.first_turn_assessor import format_brief_assessment_message
from app.agents.literature_intent import (
    LiteratureIntentResult,
    build_session_turn_context,
    execute_manage_library,
    merge_gen_constraints,
    route_literature_intent,
)
from app.agents.literature_outline import resolve_outline_plan
from app.agents.literature_planner import (
    load_planner_context,
    stream_understanding_and_route,
)
from app.agents.literature_router import should_auto_rename_session, title_is_message_truncation
from app.agents.review_prompt import citation_format_label
from app.agents.session_corpus import (
    SessionCorpus,
    resolve_session_corpus,
)
from app.agents.search_credential_hint import search_credential_secret_hint
from app.agents.url_list import sanitize_fetch_urls
from app.agents.workflow_graph import (
    apply_fetch_provider_label,
    build_literature_graph,
    build_literature_graph_legacy,
)
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.agents.execution_trace import new_trace, upsert_stage
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.schemas.literature_outline import LiteratureOutline
from app.services.llm_service import get_planner_llm, get_review_llm
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn, yield_clarification_pause
from app.agents.literature_turn_graph import (
    publish_workflow_graph as _publish_workflow_graph,
    sync_graph_nodes,
)
from app.agents.literature_turn_generate import GenerateTurnContext, stream_generate_turn
from app.agents.literature_turn_pipeline import RetrievalPipelineContext, run_retrieval_pipeline
from app.agents.literature_turn_helpers import (
    intent_needs_web_search as _intent_needs_web_search,
    last_assistant_failed as _last_assistant_failed,
    new_id as _new_id,
    section_specs_for_graph as _section_specs_for_graph,
)
from app.storage.file_store import get_store

_log = logging.getLogger(__name__)


async def stream_literature_turn(
    session_id: str,
    user_message: str,
    *,
    extra_fetch_urls: list[str] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    store = get_store()
    store.append_message(session_id, "user", user_message)

    citation_format = await get_citation_format()
    fmt_label = citation_format_label(citation_format)

    yield skill_active_event("literature-review")

    session_meta = store.get_session(session_id) or {}
    msgs = store.load_messages(session_id, limit=50)
    user_turns = sum(1 for m in msgs if m.get("role") == "user")
    last_failed = _last_assistant_failed(msgs)
    has_review = bool(store.get_latest_review(session_id))
    corpus = resolve_session_corpus(store, session_id) or SessionCorpus()

    turn_ctx = build_session_turn_context(
        session_id=session_id,
        session_meta=session_meta,
        user_turns=user_turns,
        corpus=corpus if (corpus.fetch_hits or corpus.sources_md) else None,
        last_failed=last_failed,
        has_review=has_review,
    )

    clar_state = ClarificationState.from_session(session_meta)
    pending_gate = ClarificationGate.from_dict(session_meta.get("pending_gate"))
    route_message = user_message
    skip_to_generate = False

    if pending_gate:
        resolution = resolve_pending_gate(pending_gate, user_message)
        gate_resolved = clar_state.mark_resolved(pending_gate.kind)
        clar_state.apply(resolution)
        meta_patch: dict[str, Any] = {
            "pending_gate": None,
            "gate_resolved": gate_resolved,
        }
        if resolution.action == "abort":
            meta_patch["resume_mode"] = None
            store.patch_session_meta(session_id, meta_patch)
            abort_msg = "已按你的要求取消本轮操作。"
            yield ("text", {"delta": abort_msg})
            execution_trace = new_trace()
            think_acc = ThinkAccumulator()
            await finalize_turn(
                TurnFinalizeContext(
                    store=store,
                    session_id=session_id,
                    session_meta=session_meta,
                    session_title=str(session_meta.get("title") or ""),
                    intent=LiteratureIntentResult(intent="new_topic"),
                    user_message=user_message,
                    corpus=corpus,
                    execution_trace=execution_trace,
                    think_acc=think_acc,
                    fetch_results=[],
                    cite_records=[],
                    failed_literature=[],
                    gen_constraints=list(session_meta.get("gen_constraints") or []),
                ),
                main_text=abort_msg,
            )
            yield ("stage", {"name": "完成", "state": "done"})
            return
        if pending_gate.kind == "first_turn":
            original = str(pending_gate.context.get("original_message") or "")
            route_message = merge_first_turn_message(original, resolution.merge_text)
        if pending_gate.kind == "outline_confirm":
            skip_to_generate = True
            meta_patch["resume_mode"] = "generate_only"
        store.patch_session_meta(session_id, meta_patch)
        session_meta = store.get_session(session_id) or session_meta

    if (
        not skip_to_generate
        and str(session_meta.get("resume_mode") or "") == "generate_only"
    ):
        skip_to_generate = True

    intent = await route_literature_intent(
        route_message,
        turn_ctx=turn_ctx,
        extra_urls=extra_fetch_urls,
        corpus=corpus if turn_ctx.has_corpus else None,
        last_failed=last_failed,
    )

    search_api_key = await get_web_search_api_key()
    search_provider = await get_web_search_provider()
    if _intent_needs_web_search(intent) and search_provider not in ("openalex", "native"):
        if not search_api_key:
            from app.agents.tools.web_providers import search_provider_display

            label = search_provider_display(search_provider)
            yield ("error", {"message": f"请先在设置页配置 {label} API Key"})
            return
        if search_provider == "tavily":
            key_hint = search_credential_secret_hint("tavily", search_api_key)
            if key_hint:
                yield ("error", {"message": key_hint})
                return

    search_max_results = await get_search_max_results()
    max_fetch_urls = await get_max_fetch_urls()
    source_mode = await get_literature_source_mode()
    search_retry_count = await get_search_retry_count()
    fetch_retry_count = await get_fetch_retry_count()
    fetch_retry_delay_ms = await get_fetch_retry_delay_ms()
    search_include_domains = await get_search_include_domains()
    search_exclude_domains = await get_search_exclude_domains()
    search_depth = await get_search_depth()
    search_enforce_domain_filter = await get_search_enforce_domain_filter()
    search_enable_junk_filter = await get_search_enable_junk_filter()
    max_source_chars = await get_max_source_chars()
    enable_paper_attributes = await get_enable_paper_attributes()
    enable_query_expansion = await get_enable_query_expansion()
    search_expansion_count = await get_search_expansion_count()
    outline_mode = await get_outline_mode()
    post_refine_mode = await get_post_refine_mode()
    upload_urls = sanitize_fetch_urls(extra_fetch_urls)
    if intent.new_urls:
        upload_urls = sanitize_fetch_urls(intent.new_urls + upload_urls)
    if clar_state.extra_urls:
        upload_urls = sanitize_fetch_urls(clar_state.extra_urls + upload_urls)

    graph_artifact_id = _new_id("wf")
    emitter = WorkflowNodeEmitter(graph_artifact_id)
    fetch_provider = await get_web_fetch_provider()
    g = build_literature_graph_legacy()
    apply_fetch_provider_label(g, fetch_provider)
    async for ev in _publish_workflow_graph(g, graph_artifact_id):
        yield ev
    use_outline_path = False
    outline_draft: LiteratureOutline | None = None
    outline_obj: LiteratureOutline | None = None
    sub_topics_for_search: list[Any] = []
    execution_trace = new_trace()
    think_acc = ThinkAccumulator()
    planner_ctx = await load_planner_context()
    working = SessionCorpus()
    review_llm = await get_review_llm()
    planner_llm = await get_planner_llm()
    fetch_results: list[tuple[dict[str, str], str, str | None]] = []
    cite_records: list[Any] = []
    failed_literature: list[dict[str, str]] = []
    fetch_ok = 0
    fetch_failed = 0
    hits: list[dict[str, str]] = []
    answer = ""
    gen_constraints = merge_gen_constraints(
        list(session_meta.get("gen_constraints") or []),
        intent.gen_directives if intent.intent == "refine_gen" else "",
    )
    initial_query = str(session_meta.get("initial_query") or route_message.strip())
    session_title = str(session_meta.get("title") or "")

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
        fetch_results=fetch_results,
        cite_records=cite_records,
        failed_literature=failed_literature,
        gen_constraints=gen_constraints,
    )

    if clar_state.search_relax_domain:
        search_enforce_domain_filter = False
    if clar_state.search_retry_query:
        intent.search_query = clar_state.search_retry_query

    if skip_to_generate:
        working = resolve_session_corpus(store, session_id) or SessionCorpus()
        outline_obj = LiteratureOutline.from_dict(store.load_outline(session_id))
        if not working.sources_md and not working.fetch_hits:
            fail_msg = "没有可用的文献材料，无法继续撰写。请先完成检索与抓取。"
            yield ("text", {"delta": fail_msg})
            finalize_ctx.corpus = working
            finalize_ctx.fetch_results = []
            finalize_ctx.cite_records = []
            finalize_ctx.failed_literature = list(working.failed_literature)
            finalize_ctx.intent = intent
            await finalize_turn(finalize_ctx, main_text=fail_msg)
            store.patch_session_meta(session_id, {"resume_mode": None})
            yield ("stage", {"name": "完成", "state": "done"})
            return
        if not outline_obj or not outline_obj.sections:
            fail_msg = "未找到可确认的大纲。请重新描述研究主题或关闭「计划确认」后重试。"
            yield ("text", {"delta": fail_msg})
            finalize_ctx.corpus = working
            finalize_ctx.fetch_results = []
            finalize_ctx.cite_records = []
            finalize_ctx.failed_literature = list(working.failed_literature)
            finalize_ctx.intent = intent
            await finalize_turn(finalize_ctx, main_text=fail_msg)
            store.patch_session_meta(session_id, {"resume_mode": None})
            yield ("stage", {"name": "完成", "state": "done"})
            return
        use_outline_path = True
        outline_draft = outline_obj
        if clar_state.outline_edit_directives:
            gen_constraints = merge_gen_constraints(
                gen_constraints,
                clar_state.outline_edit_directives,
            )
            intent = LiteratureIntentResult(
                intent="refine_gen",
                gen_directives=clar_state.outline_edit_directives,
            )
        fetch_results = list(working.fetch_results)
        failed_literature = list(working.failed_literature)
        fetch_ok = len(working.fetch_hits)
        fetch_failed = len(failed_literature)
        g = build_literature_graph(_section_specs_for_graph(outline_obj))
        apply_fetch_provider_label(g, fetch_provider)
        async for ev in _publish_workflow_graph(g, graph_artifact_id):
            yield ev
        prefix_done = ["fetch", "cite_extract"]
        if enable_paper_attributes and g.node("attributes"):
            prefix_done.append("attributes")
        if g.node("outline"):
            prefix_done.append("outline")
        async for ev in sync_graph_nodes(
            emitter, g, graph_artifact_id, prefix_done, "done"
        ):
            yield ev
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
        yield ("stage", {"name": "继续撰写", "state": "done"})
        upsert_stage(execution_trace, "继续撰写", "done")
    else:
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

        yield ("stage", {"name": "理解研究问题", "state": "active"})

        router_result = intent.to_router_result()
        async for ev in stream_understanding_and_route(
            route_message,
            think_acc=think_acc,
            ctx=planner_ctx,
        ):
            if ev[0] == "__router_result__":
                router_result = ev[1]["result"]
            else:
                yield ev

        if should_auto_rename_session(
            session_meta,
            route_message,
            user_message_count=user_turns,
        ):
            new_title = router_result.session_title or intent.session_title
            if new_title and title_is_message_truncation(new_title, route_message):
                new_title = ""
            if new_title:
                store.update_session(
                    session_id,
                    title=new_title,
                    title_auto_set=True,
                )
                yield (
                    "session_title",
                    {"session_id": session_id, "title": new_title},
                )

        yield ("stage", {"name": "理解研究问题", "state": "done"})
        upsert_stage(execution_trace, "理解研究问题", "done")

        search_query_for_plan = (
            router_result.search_query.strip()
            or intent.search_query
            or route_message.strip()
        )
        planner_llm = await get_planner_llm()
        first_gate, brief_assessment = await assess_first_turn_gate(
            route_message,
            search_query=search_query_for_plan,
            user_turns=user_turns,
            intent=intent.intent,
            gate_resolved=clar_state.resolved,
            llm=planner_llm,
        )
        if brief_assessment and not first_gate:
            assess_patch: dict[str, Any] = {
                "brief_assessment": brief_assessment.to_dict(),
            }
            if brief_assessment.search_query_hint:
                assess_patch["initial_query"] = route_message.strip()
            store.patch_session_meta(session_id, assess_patch)
            session_meta = store.get_session(session_id) or session_meta
            if brief_assessment.search_query_hint:
                search_query_for_plan = brief_assessment.search_query_hint
                intent.search_query = brief_assessment.search_query_hint
            rq_msg = format_brief_assessment_message(brief_assessment)
            if rq_msg:
                finalize_ctx.assistant_prefix = rq_msg
                yield ("text", {"delta": rq_msg})
            yield (
                "literature_brief_assessment",
                {
                    "core_research_questions": brief_assessment.core_research_questions,
                    "keywords": brief_assessment.keywords,
                    "search_query_hint": brief_assessment.search_query_hint,
                    "confidence": brief_assessment.confidence,
                },
            )
        if first_gate:
            finalize_ctx.corpus = corpus
            finalize_ctx.fetch_results = []
            finalize_ctx.cite_records = []
            finalize_ctx.failed_literature = []
            async for ev in yield_clarification_pause(
                first_gate,
                finalize_ctx,
                gate_resolved=clar_state.resolved,
            ):
                yield ev
            return

        initial_query = str(
            session_meta.get("initial_query") or route_message.strip()
        )
        session_title = str(session_meta.get("title") or "")

        stored_outline = LiteratureOutline.from_dict(store.load_outline(session_id))
        use_outline_path, outline_draft, sub_topics_for_search = resolve_outline_plan(
            outline_mode=outline_mode,
            intent=intent.intent,
            user_message=route_message,
            initial_query=initial_query,
            search_query=search_query_for_plan,
            session_title=session_title,
            stored_outline=stored_outline,
        )
        if use_outline_path and outline_draft:
            g = build_literature_graph(_section_specs_for_graph(outline_draft))
        else:
            g = build_literature_graph_legacy()
        apply_fetch_provider_label(g, fetch_provider)
        async for ev in _publish_workflow_graph(g, graph_artifact_id):
            yield ev

        if use_outline_path and sub_topics_for_search:
            yield (
                "literature_subtopic_plan",
                {
                    "count": len(sub_topics_for_search),
                    "sub_topics": [
                        {
                            "id": st.id,
                            "title": st.title,
                            "search_query": st.search_query,
                        }
                        for st in sub_topics_for_search
                    ],
                },
            )

        if intent.intent == "manage_library":
            async for ev in emit_system_think_line(
                "正在处理文献库管理指令…",
                accumulator=think_acc,
            ):
                yield ev
            action = intent.manage_action or "list"
            targets = intent.manage_targets
            if not action:
                from app.agents.literature_intent import parse_manage_command

                action, targets = parse_manage_command(user_message, session_id)
            main_text = execute_manage_library(action, targets, session_id)
            yield ("text", {"delta": main_text})
            upsert_stage(execution_trace, "完成", "done")
            finalize_ctx.corpus = corpus
            finalize_ctx.fetch_results = []
            finalize_ctx.cite_records = []
            finalize_ctx.failed_literature = corpus.failed_literature
            finalize_ctx.intent = intent
            await finalize_turn(finalize_ctx, main_text=main_text)
            yield ("stage", {"name": "完成", "state": "done"})
            return

        if intent.use_existing_corpus and turn_ctx.has_corpus:
            working = SessionCorpus.from_dict(corpus.to_dict()) or SessionCorpus()

        fetch_api_key = await get_fetch_api_key()
        parallel = await get_fetch_parallel()
        timeout_sec = await get_fetch_timeout_sec()

        pipe_ctx = RetrievalPipelineContext(
            session_id=session_id,
            user_message=user_message,
            route_message=route_message,
            session_title=session_title,
            search_query_for_plan=search_query_for_plan,
            intent=intent,
            router_result=router_result,
            turn_ctx=turn_ctx,
            clar_state=clar_state,
            finalize_ctx=finalize_ctx,
            store=store,
            planner_llm=planner_llm,
            emitter=emitter,
            graph=g,
            graph_artifact_id=graph_artifact_id,
            execution_trace=execution_trace,
            think_acc=think_acc,
            planner_ctx=planner_ctx,
            citation_format=citation_format,
            fmt_label=fmt_label,
            source_mode=source_mode,
            search_api_key=search_api_key,
            search_max_results=search_max_results,
            search_retry_count=search_retry_count,
            fetch_retry_delay_ms=fetch_retry_delay_ms,
            search_include_domains=search_include_domains,
            search_exclude_domains=search_exclude_domains,
            search_depth=search_depth,
            search_enforce_domain_filter=search_enforce_domain_filter,
            search_enable_junk_filter=search_enable_junk_filter,
            enable_query_expansion=enable_query_expansion,
            search_expansion_count=search_expansion_count,
            enable_paper_attributes=enable_paper_attributes,
            max_fetch_urls=max_fetch_urls,
            max_source_chars=max_source_chars,
            fetch_api_key=fetch_api_key,
            parallel=parallel,
            timeout_sec=timeout_sec,
            fetch_retry_count=fetch_retry_count,
            upload_urls=upload_urls,
            working=working,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            hits=hits,
            answer=answer,
            fetch_ok=fetch_ok,
            fetch_failed=fetch_failed,
            use_outline_path=use_outline_path,
            outline_draft=outline_draft,
            outline_obj=outline_obj,
            sub_topics_for_search=sub_topics_for_search,
            search_provider=search_provider,
            fetch_provider=fetch_provider,
        )
        async for ev in run_retrieval_pipeline(pipe_ctx):
            yield ev
        if pipe_ctx.early_return:
            return
        working = pipe_ctx.working
        fetch_results = pipe_ctx.fetch_results
        cite_records = pipe_ctx.cite_records
        failed_literature = pipe_ctx.failed_literature
        hits = pipe_ctx.hits
        answer = pipe_ctx.answer
        fetch_ok = pipe_ctx.fetch_ok
        fetch_failed = pipe_ctx.fetch_failed
        outline_obj = pipe_ctx.outline_obj
        outline_draft = pipe_ctx.outline_draft

    if not skip_to_generate and not working.sources_md and not working.fetch_hits:
        fail_msg = "没有可用的文献材料。请先提供研究问题或文献链接。"
        yield ("text", {"delta": fail_msg})
        finalize_ctx.corpus = working
        finalize_ctx.fetch_results = fetch_results
        finalize_ctx.cite_records = cite_records
        finalize_ctx.failed_literature = failed_literature
        finalize_ctx.intent = intent
        await finalize_turn(finalize_ctx, main_text=fail_msg)
        return

    if intent.defer_generate:
        summary = (
            f"已补充/更新文献语料（共 {working.source_block_count()} 个材料块）。"
            " 按你的要求暂未生成综述；需要时请说明写作要求。"
        )
        yield ("text", {"delta": summary})
        upsert_stage(execution_trace, "完成", "done")
        finalize_ctx.corpus = working
        finalize_ctx.fetch_results = fetch_results
        finalize_ctx.cite_records = cite_records
        finalize_ctx.failed_literature = failed_literature
        finalize_ctx.intent = intent
        lib_result = await finalize_turn(finalize_ctx, main_text=summary)
        yield (
            "extension",
            {"name": "library_updated", "version": "1.0", "data": lib_result},
        )
        yield ("stage", {"name": "完成", "state": "done"})
        return

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
        post_refine_mode=post_refine_mode,
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
        fetch_results=fetch_results,
        cite_records=cite_records,
        failed_literature=failed_literature,
        fetch_ok=fetch_ok,
        fetch_failed=fetch_failed,
        use_outline_path=use_outline_path,
        outline_obj=outline_obj,
    )
    async for ev in stream_generate_turn(gen_ctx):
        yield ev

