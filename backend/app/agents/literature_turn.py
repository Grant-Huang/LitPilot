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
    get_jina_api_key,
    get_literature_source_mode,
    get_max_fetch_urls,
    get_max_source_chars,
    get_outline_mode,
    get_post_refine_mode,
    get_review_system_prompt_template,
    get_search_expansion_count,
    get_tavily_api_key,
    get_tavily_enable_junk_filter,
    get_tavily_enforce_domain_filter,
    get_tavily_exclude_domains,
    get_tavily_include_domains,
    get_tavily_max_results,
    get_tavily_retry_count,
    get_tavily_search_depth,
)
from app.agents.agent_skills import skill_active_event
from app.agents.literature_intent import (
    QUERY_CORPUS_SYSTEM,
    LiteratureIntentResult,
    build_query_prompt,
    build_session_turn_context,
    execute_manage_library,
    merge_gen_constraints,
    route_literature_intent,
)
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
from app.agents.literature_outline import build_outline_from_sub_topics, prepare_outline
from app.agents.literature_post_refine import post_refine_review
from app.agents.section_refine import build_section_refine_plan
from app.agents.literature_section_writer import (
    stitch_review_sections,
    stream_section_generate,
)
from app.agents.research_decompose import decompose_research_brief
from app.agents.search_expansion import expand_search_queries
from app.agents.literature_planner import (
    format_generate_context,
    load_planner_context,
    narrate_phase_stream,
    stream_understanding_and_route,
)
from app.agents.literature_router import should_auto_rename_session
from app.agents.literature_source import should_skip_tavily
from app.agents.report_compliance import append_compliance_footer
from app.agents.review_prompt import (
    build_review_materials_user_prompt,
    build_review_turn_system_prompt,
)
from app.agents.session_corpus import (
    SessionCorpus,
    resolve_session_corpus,
    save_session_corpus,
)
from app.agents.synthesis_matrix_prompt import (
    SYNTHESIS_MATRIX_LANG,
    build_synthesis_matrix_system_prompt,
    build_synthesis_matrix_user_prompt,
)
from app.agents.tavily_key import tavily_key_hint
from app.agents.url_list import effective_fetch_cap, sanitize_fetch_urls
from app.agents.workflow_graph import build_literature_graph, build_literature_graph_legacy
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.agents.execution_trace import new_trace, upsert_stage
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.library.from_run import upsert_library_from_run
from app.llm.base import LLMMessage
from app.schemas.literature_outline import LiteratureOutline
from app.services.llm_service import get_llm, get_planner_llm
from app.storage.file_store import get_store

MAX_SOURCE_CHARS = 14_000
WORKFLOW_ARTIFACT_LANG = "workflow-graph"
_log = logging.getLogger(__name__)

_CITATION_FORMAT_LABELS = {
    "apa": "APA",
    "acm": "ACM",
}


def _new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _augment_query(user_message: str) -> str:
    from app.agents.tools.tavily_search import augment_literature_search_query

    return augment_literature_search_query(user_message)


async def _publish_workflow_graph(graph, graph_artifact_id: str):
    yield (
        "artifact",
        {
            "id": graph_artifact_id,
            "lang": WORKFLOW_ARTIFACT_LANG,
            "delta": graph.to_json(),
            "done": True,
        },
    )


async def _sync_graph_node(
    emitter,
    graph,
    graph_artifact_id: str,
    node_id: str,
    status: str,
    *,
    parent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
):
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
    elif status == "skipped":
        async for ev in emitter.yield_finish(
            node_id, "skipped", parent_id=parent_id, metadata=metadata
        ):
            yield ev


def _last_assistant_failed(msgs: list[dict[str, Any]]) -> list[dict[str, str]]:
    for msg in reversed(msgs):
        if msg.get("role") != "assistant":
            continue
        meta = msg.get("meta") or {}
        failed = meta.get("failed_literature") or []
        if failed:
            return [dict(f) for f in failed]
    return []


def _intent_needs_tavily(intent: LiteratureIntentResult) -> bool:
    if intent.intent in ("query_corpus", "manage_library", "refine_gen", "regen_only"):
        return False
    if intent.skip_tavily:
        return False
    return intent.intent in (
        "new_topic",
        "expand_search",
        "supplement",
        "synthesis_matrix",
    )


_OUTLINE_GEN_INTENTS = frozenset(
    {"new_topic", "expand_search", "supplement", "refine_gen", "regen_only"}
)


def _should_use_outline_path(
    outline_mode: str,
    sub_topic_count: int,
    intent: str,
) -> bool:
    if intent in ("query_corpus", "synthesis_matrix", "manage_library"):
        return False
    if outline_mode == "off":
        return False
    if outline_mode == "full":
        return intent in _OUTLINE_GEN_INTENTS
    return sub_topic_count >= 2 and intent in (
        "new_topic",
        "expand_search",
        "supplement",
        "regen_only",
    )


def _section_specs_for_graph(outline: LiteratureOutline) -> list[tuple[str, str]]:
    return [(s.id, s.title) for s in outline.sections]


def _resolve_outline_plan(
    *,
    outline_mode: str,
    intent: str,
    user_message: str,
    initial_query: str,
    search_query: str,
    session_title: str,
    stored_outline: LiteratureOutline | None,
) -> tuple[bool, LiteratureOutline | None, list[Any]]:
    from app.schemas.literature_outline import ResearchSubTopic

    sub_topics: list[ResearchSubTopic] = decompose_research_brief(
        initial_query or user_message,
        base_query=search_query,
    )
    use = _should_use_outline_path(
        outline_mode,
        len(sub_topics) if sub_topics else 1,
        intent,
    )
    if intent in ("refine_gen", "regen_only") and stored_outline and stored_outline.sections:
        if outline_mode != "off":
            return True, stored_outline, list(stored_outline.sub_topics)

    if not use:
        return False, None, sub_topics

    topic = (session_title or search_query or user_message).strip()[:120]
    if sub_topics:
        outline = build_outline_from_sub_topics(
            topic=topic,
            sub_topics=sub_topics,
            user_message=user_message,
        )
    else:
        outline = prepare_outline(
            user_message=initial_query or user_message,
            search_query=search_query,
            session_title=session_title,
        )
    return True, outline, list(outline.sub_topics)


async def _finalize_turn(
    *,
    store,
    session_id: str,
    session_meta: dict[str, Any],
    session_title: str,
    intent: LiteratureIntentResult,
    user_message: str,
    corpus: SessionCorpus,
    execution_trace: dict[str, Any],
    think_acc: ThinkAccumulator,
    fetch_results: list[tuple[dict[str, str], str, str | None]],
    cite_records: list[Any],
    failed_literature: list[dict[str, str]],
    main_text: str,
    gen_constraints: list[str],
    is_review: bool,
) -> dict[str, Any]:
    save_session_corpus(store, session_id, corpus)

    patch: dict[str, Any] = {
        "gen_constraints": gen_constraints,
        "last_intent": intent.intent,
        "last_failed_literature": failed_literature,
    }
    if not session_meta.get("initial_query") and intent.intent == "new_topic":
        patch["initial_query"] = user_message.strip()
    store.patch_session_meta(session_id, patch)

    lib_result: dict[str, Any] = {"added": 0, "merged": 0, "item_ids": [], "total": 0}
    if fetch_results or cite_records:
        lib_result = upsert_library_from_run(
            session_id,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            review_text=main_text if is_review else "",
            citation_format=await get_citation_format(),
            session_title=session_title,
        )

    think_text = think_acc.finalize()
    if think_text:
        execution_trace["thinkContent"] = think_text

    msg_meta: dict[str, Any] = {
        "execution_trace": execution_trace,
        "intent": intent.intent,
    }
    if think_text:
        msg_meta["think"] = think_text
    if failed_literature:
        msg_meta["failed_literature"] = failed_literature
    msg_meta["library_item_ids"] = lib_result.get("item_ids") or []
    store.append_message(session_id, "assistant", main_text, meta=msg_meta)
    return lib_result


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

    intent = await route_literature_intent(
        user_message,
        turn_ctx=turn_ctx,
        extra_urls=extra_fetch_urls,
        corpus=corpus if turn_ctx.has_corpus else None,
        last_failed=last_failed,
    )

    tavily_key = await get_tavily_api_key()
    if _intent_needs_tavily(intent):
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
    tavily_include_domains = await get_tavily_include_domains()
    tavily_exclude_domains = await get_tavily_exclude_domains()
    tavily_search_depth = await get_tavily_search_depth()
    tavily_enforce_domain_filter = await get_tavily_enforce_domain_filter()
    tavily_enable_junk_filter = await get_tavily_enable_junk_filter()
    max_source_chars = await get_max_source_chars()
    enable_paper_attributes = await get_enable_paper_attributes()
    enable_query_expansion = await get_enable_query_expansion()
    search_expansion_count = await get_search_expansion_count()
    outline_mode = await get_outline_mode()
    post_refine_mode = await get_post_refine_mode()
    upload_urls = sanitize_fetch_urls(extra_fetch_urls)
    if intent.new_urls:
        upload_urls = sanitize_fetch_urls(intent.new_urls + upload_urls)

    graph_artifact_id = _new_id("wf")
    emitter = WorkflowNodeEmitter(graph_artifact_id)
    g = build_literature_graph_legacy()
    use_outline_path = False
    outline_draft: LiteratureOutline | None = None
    sub_topics_for_search: list[Any] = []
    execution_trace = new_trace()
    think_acc = ThinkAccumulator()
    planner_ctx = await load_planner_context()

    yield (
        "literature_intent",
        {
            "intent": intent.intent,
            "defer_generate": intent.defer_generate,
            "skip_tavily": intent.skip_tavily,
            "skip_fetch": intent.skip_fetch,
            "use_existing_corpus": intent.use_existing_corpus,
        },
    )

    yield ("stage", {"name": "理解研究问题", "state": "active"})

    router_result = intent.to_router_result()
    async for ev in stream_understanding_and_route(
        user_message,
        think_acc=think_acc,
        ctx=planner_ctx,
    ):
        if ev[0] == "__router_result__":
            router_result = ev[1]["result"]
        else:
            yield ev

    if should_auto_rename_session(
        session_meta,
        user_message,
        user_message_count=user_turns,
    ):
        new_title = router_result.session_title or intent.session_title
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

    gen_constraints = merge_gen_constraints(
        list(session_meta.get("gen_constraints") or []),
        intent.gen_directives if intent.intent == "refine_gen" else "",
    )
    initial_query = str(
        session_meta.get("initial_query") or user_message.strip()
    )
    session_title = str(session_meta.get("title") or "")

    search_query_for_plan = (
        intent.search_query
        or router_result.search_query.strip()
        or user_message.strip()
    )
    stored_outline = LiteratureOutline.from_dict(store.load_outline(session_id))
    use_outline_path, outline_draft, sub_topics_for_search = _resolve_outline_plan(
        outline_mode=outline_mode,
        intent=intent.intent,
        user_message=user_message,
        initial_query=initial_query,
        search_query=search_query_for_plan,
        session_title=session_title,
        stored_outline=stored_outline,
    )
    if use_outline_path and outline_draft:
        g = build_literature_graph(_section_specs_for_graph(outline_draft))
    else:
        g = build_literature_graph_legacy()
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
        await _finalize_turn(
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
            failed_literature=corpus.failed_literature,
            main_text=main_text,
            gen_constraints=gen_constraints,
            is_review=False,
        )
        yield ("stage", {"name": "完成", "state": "done"})
        return

    working = SessionCorpus()
    if intent.use_existing_corpus and turn_ctx.has_corpus:
        working = SessionCorpus.from_dict(corpus.to_dict()) or SessionCorpus()

    llm = await get_llm()
    jina_key = await get_jina_api_key()
    parallel = await get_fetch_parallel()
    timeout_sec = await get_fetch_timeout_sec()

    hits: list[dict[str, str]] = []
    answer = ""
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
        retry_urls = upload_urls or intent.new_urls
        if retry_urls:
            hits = user_url_hits(retry_urls)
            run_fetch = True
        else:
            yield ("text", {"delta": "没有可重试的失败链接。"})
            upsert_stage(execution_trace, "完成", "done")
            await _finalize_turn(
                store=store,
                session_id=session_id,
                session_meta=session_meta,
                session_title=session_title,
                intent=intent,
                user_message=user_message,
                corpus=working,
                execution_trace=execution_trace,
                think_acc=think_acc,
                fetch_results=[],
                cite_records=[],
                failed_literature=working.failed_literature,
                main_text="没有可重试的失败链接。",
                gen_constraints=gen_constraints,
                is_review=False,
            )
            yield ("stage", {"name": "完成", "state": "done"})
            return

    if run_search:
        base_query = (
            intent.search_query
            or router_result.search_query.strip()
            or user_message.strip()
        )
        query = _augment_query(base_query)
        skip_tavily = should_skip_tavily(source_mode, upload_urls)
        if intent.skip_tavily:
            skip_tavily = True
        search_out: dict[str, Any] = {}
        try:
            expanded_queries = [query]
            if (
                use_outline_path
                and len(sub_topics_for_search) >= 2
                and not skip_tavily
            ):
                expanded_queries = [
                    _augment_query(str(st.search_query or query))
                    for st in sub_topics_for_search
                ]
            elif enable_query_expansion and search_expansion_count > 1:
                planner_llm = await get_planner_llm()
                expanded_queries = await expand_search_queries(
                    query,
                    count=search_expansion_count,
                    user_message=user_message,
                    llm=planner_llm,
                    use_llm=True,
                )

            if len(expanded_queries) > 1:
                async for ev in stream_expanded_search_phase(
                    user_message=user_message,
                    queries=expanded_queries,
                    tavily_key=tavily_key or "",
                    tavily_max_results=tavily_max_results,
                    tavily_retry_count=tavily_retry_count,
                    fetch_retry_delay_ms=fetch_retry_delay_ms,
                    source_mode=source_mode,
                    upload_count=len(upload_urls),
                    skip_tavily=skip_tavily,
                    upload_urls=upload_urls,
                    think_acc=think_acc,
                    planner_ctx=planner_ctx,
                    execution_trace=execution_trace,
                    corpus=working if turn_ctx.has_corpus else None,
                    result=search_out,
                    tavily_include_domains=tavily_include_domains,
                    tavily_exclude_domains=tavily_exclude_domains,
                    tavily_search_depth=tavily_search_depth,
                    tavily_enforce_domain_filter=tavily_enforce_domain_filter,
                    tavily_enable_junk_filter=tavily_enable_junk_filter,
                ):
                    yield ev
            else:
                async for ev in stream_search_phase(
                    user_message=user_message,
                    query=query,
                    tavily_key=tavily_key or "",
                    tavily_max_results=tavily_max_results,
                    tavily_retry_count=tavily_retry_count,
                    fetch_retry_delay_ms=fetch_retry_delay_ms,
                    source_mode=source_mode,
                    upload_count=len(upload_urls),
                    skip_tavily=skip_tavily,
                    upload_urls=upload_urls,
                    think_acc=think_acc,
                    planner_ctx=planner_ctx,
                    execution_trace=execution_trace,
                    corpus=working if turn_ctx.has_corpus else None,
                    result=search_out,
                    tavily_include_domains=tavily_include_domains,
                    tavily_exclude_domains=tavily_exclude_domains,
                    tavily_search_depth=tavily_search_depth,
                    tavily_enforce_domain_filter=tavily_enforce_domain_filter,
                    tavily_enable_junk_filter=tavily_enable_junk_filter,
                ):
                    yield ev
        except ValueError as e:
            fail_msg = str(e)
            yield ("text", {"delta": fail_msg})
            await _finalize_turn(
                store=store,
                session_id=session_id,
                session_meta=session_meta,
                session_title=session_title,
                intent=intent,
                user_message=user_message,
                corpus=working,
                execution_trace=execution_trace,
                think_acc=think_acc,
                fetch_results=[],
                cite_records=[],
                failed_literature=working.failed_literature,
                main_text=fail_msg,
                gen_constraints=gen_constraints,
                is_review=False,
            )
            return
        except Exception as e:
            if not upload_urls:
                fail_msg = f"Tavily 搜索不可用（{e}）。请检查 API Key；本次会话已终止。"
                yield ("text", {"delta": fail_msg})
                await _finalize_turn(
                    store=store,
                    session_id=session_id,
                    session_meta=session_meta,
                    session_title=session_title,
                    intent=intent,
                    user_message=user_message,
                    corpus=working,
                    execution_trace=execution_trace,
                    think_acc=think_acc,
                    fetch_results=[],
                    cite_records=[],
                    failed_literature=working.failed_literature,
                    main_text=fail_msg,
                    gen_constraints=gen_constraints,
                    is_review=False,
                )
                return
            async for ev in emit_system_think_line(
                f"Tavily 检索失败，将仅使用用户链接（{len(upload_urls)} 条）。",
                accumulator=think_acc,
            ):
                yield ev

        hits = list(search_out.get("hits") or [])
        answer = str(search_out.get("answer") or "")

    fetch_cap = effective_fetch_cap(max_fetch_urls, upload_urls)
    fetch_hits: list[dict[str, str]] = []
    fetch_results: list[tuple[dict[str, str], str, str | None]] = []
    cite_records: list[Any] = []
    fetch_ok = 0
    fetch_failed = 0
    failed_literature: list[dict[str, str]] = []

    if run_fetch:
        if upload_urls and not hits:
            build_result = build_fetch_queue(
                source_mode="user_only",
                hits=[],
                user_urls=upload_urls,
                fetch_cap=fetch_cap,
            )
        else:
            build_result = build_fetch_queue(
                source_mode=source_mode,
                hits=hits,
                user_urls=upload_urls,
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
                user_message=user_message,
                fetch_hits=fetch_hits,
                fetch_cap=fetch_cap,
                jina_key=jina_key,
                llm=llm,
                parallel=parallel,
                timeout_sec=timeout_sec,
                fetch_retry_count=fetch_retry_count,
                fetch_retry_delay_ms=fetch_retry_delay_ms,
                think_acc=think_acc,
                planner_ctx=planner_ctx,
                execution_trace=execution_trace,
                emitter=emitter,
                graph=g,
                graph_artifact_id=graph_artifact_id,
                sync_graph_node=_sync_graph_node,
                tavily_answer=answer,
                result=fetch_out,
                max_source_chars=max_source_chars,
            ):
                yield ev
            delta: SessionCorpus = fetch_out.get("delta") or SessionCorpus()
            fetch_ok = int(fetch_out.get("fetch_ok") or 0)
            fetch_failed = int(fetch_out.get("fetch_failed") or 0)
            working.merge(delta)
            fetch_results = list(delta.fetch_results)
            failed_literature = list(delta.failed_literature)

            cite_out: dict[str, Any] = {}
            failed_literature = list(working.failed_literature)
            async for ev in stream_cite_phase(
                user_message=user_message,
                fetch_hits=fetch_hits,
                fetch_cap=fetch_cap,
                jina_key=jina_key,
                timeout_sec=timeout_sec,
                citation_format=citation_format,
                fmt_label=fmt_label,
                session_id=session_id,
                session_title=session_title,
                think_acc=think_acc,
                planner_ctx=planner_ctx,
                execution_trace=execution_trace,
                emitter=emitter,
                graph=g,
                graph_artifact_id=graph_artifact_id,
                sync_graph_node=_sync_graph_node,
                store=store,
                failed_literature=failed_literature,
                result=cite_out,
            ):
                yield ev
            cite_records = list(cite_out.get("cite_records") or [])
            ref_text = str(cite_out.get("ref_text") or "")
            if ref_text.strip():
                block = f"## [Citations] 已收录引用\n\n{ref_text[-8000:]}\n"
                if block not in working.sources_md:
                    working.sources_md.append(block)
        elif intent.intent in ("supplement", "retry_failed", "expand_search"):
            msg = "没有新的文献链接需要抓取（可能已全部在库中）。"
            async for ev in emit_system_think_line(msg, accumulator=think_acc):
                yield ev
            if intent.defer_generate:
                yield ("text", {"delta": msg})
                upsert_stage(execution_trace, "完成", "done")
                await _finalize_turn(
                    store=store,
                    session_id=session_id,
                    session_meta=session_meta,
                    session_title=session_title,
                    intent=intent,
                    user_message=user_message,
                    corpus=working,
                    execution_trace=execution_trace,
                    think_acc=think_acc,
                    fetch_results=[],
                    cite_records=[],
                    failed_literature=working.failed_literature,
                    main_text=msg,
                    gen_constraints=gen_constraints,
                    is_review=False,
                )
                yield ("stage", {"name": "完成", "state": "done"})
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
            accumulator=think_acc,
        ):
            yield ev
        upsert_stage(execution_trace, "文献检索", "skipped")
        upsert_stage(execution_trace, "抓取网页", "skipped")
        upsert_stage(execution_trace, "引用抽取", "skipped")
        failed_literature = list(working.failed_literature)
        fetch_results = list(working.fetch_results)

    if enable_paper_attributes and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        attr_fetch_results = list(fetch_results) or list(working.fetch_results)
        if attr_fetch_results or working.paper_index:
            if use_outline_path:
                async for ev in _sync_graph_node(
                    emitter,
                    g,
                    graph_artifact_id,
                    "attributes",
                    "active",
                    parent_id="cite_extract",
                ):
                    yield ev
            attr_out: dict[str, Any] = {}
            async for ev in stream_attributes_phase(
                user_message=user_message,
                corpus=working,
                fetch_results=attr_fetch_results,
                cite_records=cite_records,
                llm=llm,
                parallel=parallel,
                think_acc=think_acc,
                planner_ctx=planner_ctx,
                execution_trace=execution_trace,
                result=attr_out,
            ):
                yield ev
            if use_outline_path:
                async for ev in _sync_graph_node(
                    emitter,
                    g,
                    graph_artifact_id,
                    "attributes",
                    "done",
                    parent_id="cite_extract",
                ):
                    yield ev
    elif use_outline_path and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        async for ev in _sync_graph_node(
            emitter,
            g,
            graph_artifact_id,
            "attributes",
            "skipped",
            parent_id="cite_extract",
        ):
            yield ev

    outline_obj: LiteratureOutline | None = None
    if use_outline_path and intent.intent not in (
        "query_corpus",
        "synthesis_matrix",
        "manage_library",
    ):
        if not working.sources_md and not working.fetch_hits:
            pass
        else:
            outline_out: dict[str, Any] = {}
            async for ev in stream_outline_phase(
                user_message=user_message,
                search_query=search_query_for_plan,
                session_title=session_title,
                session_id=session_id,
                corpus=working,
                store=store,
                think_acc=think_acc,
                planner_ctx=planner_ctx,
                execution_trace=execution_trace,
                emitter=emitter,
                graph=g,
                graph_artifact_id=graph_artifact_id,
                sync_graph_node=_sync_graph_node,
                outline=outline_draft,
                result=outline_out,
            ):
                yield ev
            outline_obj = outline_out.get("outline")
            if isinstance(outline_obj, LiteratureOutline):
                outline_draft = outline_obj

    if not working.sources_md and not working.fetch_hits:
        fail_msg = "没有可用的文献材料。请先提供研究问题或文献链接。"
        yield ("text", {"delta": fail_msg})
        await _finalize_turn(
            store=store,
            session_id=session_id,
            session_meta=session_meta,
            session_title=session_title,
            intent=intent,
            user_message=user_message,
            corpus=working,
            execution_trace=execution_trace,
            think_acc=think_acc,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            main_text=fail_msg,
            gen_constraints=gen_constraints,
            is_review=False,
        )
        return

    if intent.defer_generate:
        summary = (
            f"已补充/更新文献语料（共 {working.source_block_count()} 个材料块）。"
            " 按你的要求暂未生成综述；需要时请说明写作要求。"
        )
        yield ("text", {"delta": summary})
        upsert_stage(execution_trace, "完成", "done")
        lib_result = await _finalize_turn(
            store=store,
            session_id=session_id,
            session_meta=session_meta,
            session_title=session_title,
            intent=intent,
            user_message=user_message,
            corpus=working,
            execution_trace=execution_trace,
            think_acc=think_acc,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            main_text=summary,
            gen_constraints=gen_constraints,
            is_review=False,
        )
        yield (
            "extension",
            {"name": "library_updated", "version": "1.0", "data": lib_result},
        )
        yield ("stage", {"name": "完成", "state": "done"})
        return

    context_block = "\n".join(working.sources_md)[:80_000]
    cite_ok = sum(1 for r in cite_records if getattr(r, "success", False))

    if intent.intent == "query_corpus":
        yield ("stage", {"name": "文献问答", "state": "active"})
        q_prompt = build_query_prompt(
            initial_query=initial_query,
            user_message=user_message,
            context_block=context_block,
        )
        main_parts: list[str] = []
        try:
            async for chunk in llm.chat_stream(
                [LLMMessage(role="user", content=q_prompt)],
                system=QUERY_CORPUS_SYSTEM,
                max_tokens=2048,
                temperature=0.3,
            ):
                main_parts.append(chunk)
                yield ("text", {"delta": chunk})
        except Exception as e:
            _log.exception("query_corpus streaming failed")
            err_line = f"\n\n（生成失败：{e}。请检查 LLM 配置或稍后重试。）"
            main_parts.append(err_line)
            yield ("text", {"delta": err_line})
        main_text = "".join(main_parts) or "（未能生成回答，请换种问法。）"
        upsert_stage(execution_trace, "文献问答", "done")
        upsert_stage(execution_trace, "完成", "done")
        await _finalize_turn(
            store=store,
            session_id=session_id,
            session_meta=session_meta,
            session_title=session_title,
            intent=intent,
            user_message=user_message,
            corpus=working,
            execution_trace=execution_trace,
            think_acc=think_acc,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            main_text=main_text,
            gen_constraints=gen_constraints,
            is_review=False,
        )
        yield ("stage", {"name": "完成", "state": "done"})
        return

    if intent.intent == "synthesis_matrix":
        async for ev in _sync_graph_node(
            emitter,
            g,
            graph_artifact_id,
            "generate",
            "active",
        ):
            yield ev
        yield ("stage", {"name": "矩阵生成", "state": "active"})
        async for ev in emit_system_think_line(
            "正在按论文与主题维度生成文献综述矩阵。",
            accumulator=think_acc,
        ):
            yield ev

        matrix_prompt = build_synthesis_matrix_user_prompt(context_block)
        matrix_system = build_synthesis_matrix_system_prompt(
            initial_query=initial_query,
            gen_directives=intent.gen_directives or user_message,
        )
        matrix_parts = []
        try:
            async for chunk in llm.chat_stream(
                [LLMMessage(role="user", content=matrix_prompt)],
                system=matrix_system,
                max_tokens=4096,
                temperature=0.25,
            ):
                matrix_parts.append(chunk)
                yield ("text", {"delta": chunk})
        except Exception:
            _log.exception("synthesis matrix streaming failed")

        matrix_text = "".join(matrix_parts)
        if not matrix_text.strip():
            try:
                resp = await llm.chat(
                    [LLMMessage(role="user", content=matrix_prompt)],
                    system=matrix_system,
                    max_tokens=4096,
                    temperature=0.25,
                )
                matrix_text = (resp.content or "").strip()
                if matrix_text:
                    yield ("text", {"delta": matrix_text})
            except Exception:
                _log.exception("synthesis matrix fallback failed")
                matrix_text = ""
        if not matrix_text.strip():
            matrix_text = "（矩阵生成为空：模型未返回任何内容。请缩小问题范围后重试。）\n"
            yield ("text", {"delta": matrix_text})

        main_text = append_compliance_footer(matrix_text)
        if main_text != matrix_text:
            tail = main_text[len(matrix_text) :]
            if tail:
                yield ("text", {"delta": tail})

        async for ev in _sync_graph_node(
            emitter,
            g,
            graph_artifact_id,
            "generate",
            "done",
        ):
            yield ev
        yield ("stage", {"name": "矩阵生成", "state": "done"})
        upsert_stage(execution_trace, "矩阵生成", "done")

        async for ev in _sync_graph_node(
            emitter,
            g,
            graph_artifact_id,
            "deliver",
            "active",
        ):
            yield ev

        _, version_id = store.save_matrix_artifact(session_id, main_text)
        art_id = _new_id("matrix")
        yield (
            "artifact",
            {
                "id": art_id,
                "lang": SYNTHESIS_MATRIX_LANG,
                "delta": main_text,
                "done": True,
                "version_id": version_id,
            },
        )

        async for ev in _sync_graph_node(
            emitter,
            g,
            graph_artifact_id,
            "deliver",
            "done",
        ):
            yield ev
        upsert_stage(execution_trace, "完成", "done")
        lib_result = await _finalize_turn(
            store=store,
            session_id=session_id,
            session_meta=session_meta,
            session_title=session_title,
            intent=intent,
            user_message=user_message,
            corpus=working,
            execution_trace=execution_trace,
            think_acc=think_acc,
            fetch_results=fetch_results,
            cite_records=cite_records,
            failed_literature=failed_literature,
            main_text=main_text,
            gen_constraints=gen_constraints,
            is_review=False,
        )
        yield (
            "extension",
            {"name": "library_updated", "version": "1.0", "data": lib_result},
        )
        yield ("stage", {"name": "完成", "state": "done"})
        return

    raw_main = ""
    last_wf_node = "outline" if use_outline_path and outline_obj else "cite_extract"

    if use_outline_path and outline_obj:
        yield ("stage", {"name": "综述生成", "state": "active"})
        gen_ctx = format_generate_context(
            source_blocks=len(working.sources_md),
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

        section_parts: list[tuple[Any, str]] = []
        prior = ""
        prev_node = "outline"
        gen_directives = intent.gen_directives or ""
        prior_review = store.get_latest_review(session_id)
        prior_review_text = str((prior_review or {}).get("content") or "")
        refine_plan = None
        if intent.intent in ("refine_gen", "regen_only") and prior_review_text.strip():
            refine_plan = build_section_refine_plan(
                user_message=user_message,
                outline=outline_obj,
                prior_review_text=prior_review_text,
                gen_directives=gen_directives,
            )
            if refine_plan.target_section_ids is not None:
                yield (
                    "literature_section_refine",
                    {
                        "mode": "partial",
                        "target_section_ids": refine_plan.target_section_ids,
                        "target_titles": [
                            s.title
                            for s in outline_obj.sections
                            if s.id in refine_plan.target_section_ids
                        ],
                        "reused_count": len(outline_obj.sections)
                        - len(refine_plan.target_section_ids),
                    },
                )
            elif intent.intent == "refine_gen":
                yield (
                    "literature_section_refine",
                    {"mode": "full", "target_section_ids": [], "reused_count": 0},
                )

        for section in outline_obj.sections:
            reuse_body = ""
            if refine_plan and not refine_plan.should_regenerate(section.id):
                reuse_body = refine_plan.prior_bodies.get(section.id, "")
            if reuse_body:
                async for ev in _sync_graph_node(
                    emitter,
                    g,
                    graph_artifact_id,
                    section.id,
                    "skipped",
                    parent_id=prev_node,
                    metadata={"reused": True},
                ):
                    yield ev
                section_parts.append((section, reuse_body))
                prior = (prior + "\n" + reuse_body)[-1500:]
                prev_node = section.id
                last_wf_node = section.id
                continue

            async for ev in _sync_graph_node(
                emitter,
                g,
                graph_artifact_id,
                section.id,
                "active",
                parent_id=prev_node,
            ):
                yield ev
            stage_label = f"撰写：{section.title[:24]}"
            yield ("stage", {"name": stage_label, "state": "active"})
            sec_parts: list[str] = []
            sec_is_refine = bool(
                refine_plan
                and refine_plan.prior_bodies.get(section.id, "").strip()
                and intent.intent == "refine_gen"
            )
            sec_directives = (
                refine_plan.revision_directives if refine_plan else gen_directives
            )
            try:
                async for chunk in stream_section_generate(
                    llm,
                    outline=outline_obj,
                    section=section,
                    paper_index=working.paper_index,
                    prior_excerpt=prior,
                    prior_section_body=refine_plan.prior_bodies.get(section.id, "")
                    if refine_plan
                    else "",
                    gen_directives=sec_directives,
                    is_refine=sec_is_refine,
                ):
                    sec_parts.append(chunk)
                    yield ("text", {"delta": chunk})
            except Exception:
                _log.exception("section %s streaming failed", section.id)
            sec_body = "".join(sec_parts)
            if not sec_body.strip():
                sec_body = f"（章节「{section.title}」生成为空。）\n"
                yield ("text", {"delta": sec_body})
            section_parts.append((section, sec_body))
            prior = (prior + "\n" + sec_body)[-1500:]
            async for ev in _sync_graph_node(
                emitter,
                g,
                graph_artifact_id,
                section.id,
                "done",
                parent_id=prev_node,
            ):
                yield ev
            upsert_stage(execution_trace, stage_label, "done")
            yield ("stage", {"name": stage_label, "state": "done"})
            prev_node = section.id
            last_wf_node = section.id

        raw_main = stitch_review_sections(section_parts)
        upsert_stage(execution_trace, "综述生成", "done")
        yield ("stage", {"name": "综述生成", "state": "done"})
    else:
        async for ev in _sync_graph_node(
            emitter, g, graph_artifact_id, "generate", "active"
        ):
            yield ev
        yield ("stage", {"name": "综述生成", "state": "active"})

        gen_ctx = format_generate_context(
            source_blocks=len(working.sources_md),
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

        gen_prompt = build_review_materials_user_prompt(
            context_block,
            prior_review_excerpt=(
                str((store.get_latest_review(session_id) or {}).get("content") or "")
                if intent.intent in ("refine_gen", "regen_only")
                else ""
            ),
        )
        review_template = await get_review_system_prompt_template()
        review_system = build_review_turn_system_prompt(
            citation_format,
            review_template,
            initial_query=initial_query,
            gen_constraints=gen_constraints,
            gen_directives=intent.gen_directives,
            intent=intent.intent,
        )
        main_parts: list[str] = []
        try:
            async for chunk in llm.chat_stream(
                [LLMMessage(role="user", content=gen_prompt)],
                system=review_system,
                max_tokens=4096,
                temperature=0.35,
            ):
                main_parts.append(chunk)
                yield ("text", {"delta": chunk})
        except Exception:
            _log.exception("review streaming failed")

        raw_main = "".join(main_parts)
        if not raw_main.strip():
            try:
                resp = await llm.chat(
                    [LLMMessage(role="user", content=gen_prompt)],
                    system=review_system,
                    max_tokens=4096,
                    temperature=0.35,
                )
                raw_main = (resp.content or "").strip()
                if raw_main:
                    yield ("text", {"delta": raw_main})
            except Exception:
                _log.exception("review non-stream fallback failed")
                raw_main = ""
            if not raw_main.strip():
                raw_main = "（综述生成为空：模型未返回任何内容。请缩小问题范围后重试。）\n"
                yield ("text", {"delta": raw_main})

        async for ev in _sync_graph_node(
            emitter, g, graph_artifact_id, "generate", "done"
        ):
            yield ev
        yield ("stage", {"name": "综述生成", "state": "done"})
        upsert_stage(execution_trace, "综述生成", "done")
        last_wf_node = "generate"

    if use_outline_path:
        if post_refine_mode != "off":
            async for ev in _sync_graph_node(
                emitter,
                g,
                graph_artifact_id,
                "refine",
                "active",
                parent_id=last_wf_node,
            ):
                yield ev
            refined, report = post_refine_review(
                raw_main,
                outline=outline_obj,
                cite_count=cite_ok,
            )
            raw_main = refined
            yield ("literature_refine_report", report)
            async for ev in _sync_graph_node(
                emitter,
                g,
                graph_artifact_id,
                "refine",
                "done",
                parent_id=last_wf_node,
            ):
                yield ev
            upsert_stage(execution_trace, "后处理", "done")
            deliver_parent = "refine"
        else:
            async for ev in _sync_graph_node(
                emitter,
                g,
                graph_artifact_id,
                "refine",
                "skipped",
                parent_id=last_wf_node,
            ):
                yield ev
            deliver_parent = "refine"
    else:
        deliver_parent = None

    main_text = append_compliance_footer(raw_main)
    if main_text != raw_main:
        tail = main_text[len(raw_main) :]
        if tail:
            yield ("text", {"delta": tail})

    async for ev in _sync_graph_node(
        emitter,
        g,
        graph_artifact_id,
        "deliver",
        "active",
        parent_id=deliver_parent,
    ):
        yield ev

    _, version_id = store.save_review_artifact(session_id, main_text)
    art_id = _new_id("review")
    yield (
        "artifact",
        {
            "id": art_id,
            "lang": "markdown",
            "delta": main_text,
            "done": True,
            "version_id": version_id,
        },
    )

    async for ev in _sync_graph_node(
        emitter, g, graph_artifact_id, "deliver", "done", parent_id=deliver_parent
    ):
        yield ev

    upsert_stage(execution_trace, "完成", "done")
    lib_result = await _finalize_turn(
        store=store,
        session_id=session_id,
        session_meta=session_meta,
        session_title=session_title,
        intent=intent,
        user_message=user_message,
        corpus=working,
        execution_trace=execution_trace,
        think_acc=think_acc,
        fetch_results=fetch_results,
        cite_records=cite_records,
        failed_literature=failed_literature,
        main_text=main_text,
        gen_constraints=gen_constraints,
        is_review=True,
    )
    yield (
        "extension",
        {"name": "library_updated", "version": "1.0", "data": lib_result},
    )
    yield ("stage", {"name": "完成", "state": "done"})
