"""Generation phase: query_corpus, synthesis matrix, and review delivery."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.agents.execution_trace import upsert_stage
from app.agents.literature_intent import LiteratureIntentResult, build_query_prompt
from app.agents.prompt_settings import (
    get_matrix_system_prompt,
    get_prompt_max_tokens,
    get_query_corpus_system_prompt,
)
from app.agents.literature_planner import (
    PlannerContext,
    format_generate_context,
    narrate_phase_stream,
)
from app.agents.literature_section_writer import (
    stitch_review_sections,
    stream_section_generate,
)
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn
from app.agents.literature_turn_graph import sync_graph_node
from app.agents.literature_turn_helpers import new_id
from app.agents.report_compliance import append_compliance_footer
from app.agents.section_refine import build_section_refine_plan
from app.agents.session_corpus import SessionCorpus
from app.agents.synthesis_matrix_prompt import (
    SYNTHESIS_MATRIX_LANG,
    build_synthesis_matrix_system_prompt,
    build_synthesis_matrix_user_prompt,
)
from app.agents.workflow_emitter import WorkflowNodeEmitter
from app.core.stream_events import (
    artifact_stream_delta,
    chat_text,
    clamp_corpus_answer,
)
from app.core.think_stream import ThinkAccumulator, emit_system_think_line
from app.llm.base import LLMMessage
from app.schemas.literature_outline import LiteratureOutline

_log = logging.getLogger(__name__)


@dataclass
class GenerateTurnContext:
    session_id: str
    user_message: str
    route_message: str
    initial_query: str
    session_title: str
    intent: LiteratureIntentResult
    gen_constraints: list[str]
    citation_format: str
    fmt_label: str
    finalize_ctx: TurnFinalizeContext
    store: Any
    llm: Any
    emitter: WorkflowNodeEmitter
    graph: Any
    graph_artifact_id: str
    execution_trace: dict[str, Any]
    think_acc: ThinkAccumulator
    planner_ctx: PlannerContext
    working: SessionCorpus
    fetch_results: list[tuple[dict[str, str], str, str | None]] = field(default_factory=list)
    cite_records: list[Any] = field(default_factory=list)
    failed_literature: list[dict[str, str]] = field(default_factory=list)
    fetch_ok: int = 0
    fetch_failed: int = 0
    outline_obj: LiteratureOutline | None = None
    handled: bool = False


async def stream_generate_turn(
    ctx: GenerateTurnContext,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    context_block = "\n".join(ctx.working.sources_md)[:80_000]
    cite_ok = sum(1 for r in ctx.cite_records if getattr(r, "success", False))
    intent = ctx.intent

    if intent.intent == "query_corpus":
        async for ev in _stream_query_corpus(ctx, context_block):
            yield ev
        ctx.handled = True
        return

    async for ev in _stream_review(ctx, context_block, cite_ok):
        yield ev
    ctx.handled = True


async def _stream_query_corpus(
    ctx: GenerateTurnContext,
    context_block: str,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    yield ("stage", {"name": "文献问答", "state": "active"})
    q_prompt = build_query_prompt(
        initial_query=ctx.initial_query,
        user_message=ctx.user_message,
        context_block=context_block,
    )
    main_parts: list[str] = []
    query_system = await get_query_corpus_system_prompt()
    query_tokens = await get_prompt_max_tokens("query_corpus_system_template")
    try:
        async for chunk in ctx.llm.chat_stream(
            [LLMMessage(role="user", content=q_prompt)],
            system=query_system,
            max_tokens=query_tokens,
            temperature=0.3,
        ):
            main_parts.append(chunk)
            yield chat_text(chunk)
    except Exception as e:
        _log.exception("query_corpus streaming failed")
        err_line = f"\n\n（生成失败：{e}。请检查 LLM 配置或稍后重试。）"
        main_parts.append(err_line)
        yield chat_text(err_line)
    main_text = clamp_corpus_answer("".join(main_parts) or "（未能生成回答，请换种问法。）")
    upsert_stage(ctx.execution_trace, "文献问答", "done")
    upsert_stage(ctx.execution_trace, "完成", "done")
    ctx.finalize_ctx.corpus = ctx.working
    ctx.finalize_ctx.fetch_results = ctx.fetch_results
    ctx.finalize_ctx.cite_records = ctx.cite_records
    ctx.finalize_ctx.failed_literature = ctx.failed_literature
    ctx.finalize_ctx.intent = ctx.intent
    ctx.finalize_ctx.chat_text = main_text
    _, end_ev = await finalize_turn(ctx.finalize_ctx, main_text=main_text)
    yield end_ev
    yield ("stage", {"name": "完成", "state": "done"})


async def _stream_synthesis_matrix(
    ctx: GenerateTurnContext,
    context_block: str,
    *,
    parent_id: str | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    async for ev in sync_graph_node(
        ctx.emitter,
        ctx.graph,
        ctx.graph_artifact_id,
        "matrix",
        "active",
        parent_id=parent_id,
    ):
        yield ev
    yield ("stage", {"name": "矩阵生成", "state": "active"})
    async for ev in emit_system_think_line(
        "正在按论文与主题维度生成文献综述矩阵。",
        accumulator=ctx.think_acc,
    ):
        yield ev

    matrix_prompt = build_synthesis_matrix_user_prompt(context_block)
    matrix_template = await get_matrix_system_prompt()
    matrix_system = build_synthesis_matrix_system_prompt(
        initial_query=ctx.initial_query,
        gen_directives=ctx.intent.gen_directives or ctx.user_message,
        base_template=matrix_template,
    )
    matrix_art_id = new_id("matrix")
    matrix_parts: list[str] = []
    matrix_tokens = await get_prompt_max_tokens("matrix_system_template")
    try:
        async for chunk in ctx.llm.chat_stream(
            [LLMMessage(role="user", content=matrix_prompt)],
            system=matrix_system,
            max_tokens=matrix_tokens,
            temperature=0.25,
        ):
            matrix_parts.append(chunk)
            yield artifact_stream_delta(
                matrix_art_id,
                chunk,
                lang=SYNTHESIS_MATRIX_LANG,
            )
    except Exception:
        _log.exception("synthesis matrix streaming failed")

    matrix_text = "".join(matrix_parts)
    if not matrix_text.strip():
        try:
            resp = await ctx.llm.chat(
                [LLMMessage(role="user", content=matrix_prompt)],
                system=matrix_system,
                max_tokens=matrix_tokens,
                temperature=0.25,
            )
            matrix_text = (resp.content or "").strip()
            if matrix_text:
                yield artifact_stream_delta(
                    matrix_art_id,
                    matrix_text,
                    lang=SYNTHESIS_MATRIX_LANG,
                )
        except Exception:
            _log.exception("synthesis matrix fallback failed")
            matrix_text = ""
    if not matrix_text.strip():
        matrix_text = "（矩阵生成为空：模型未返回任何内容。请缩小问题范围后重试。）\n"
        yield artifact_stream_delta(matrix_art_id, matrix_text, lang=SYNTHESIS_MATRIX_LANG)

    main_text = append_compliance_footer(matrix_text)
    if main_text != matrix_text:
        tail = main_text[len(matrix_text) :]
        if tail:
            yield artifact_stream_delta(matrix_art_id, tail, lang=SYNTHESIS_MATRIX_LANG)

    async for ev in sync_graph_node(
        ctx.emitter,
        ctx.graph,
        ctx.graph_artifact_id,
        "matrix",
        "done",
        parent_id=parent_id,
    ):
        yield ev
    yield ("stage", {"name": "矩阵生成", "state": "done"})
    upsert_stage(ctx.execution_trace, "矩阵生成", "done")

    _, matrix_version_id = ctx.store.save_matrix_artifact(ctx.session_id, main_text)
    yield artifact_stream_delta(
        matrix_art_id,
        "",
        lang=SYNTHESIS_MATRIX_LANG,
        version_id=matrix_version_id,
        done=True,
    )


async def _stream_review(
    ctx: GenerateTurnContext,
    context_block: str,
    cite_ok: int,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    raw_main = ""
    review_art_id = new_id("review")
    version_id: str | None = None
    outline_obj = ctx.outline_obj
    if not outline_obj:
        yield chat_text("未找到子主题大纲，无法生成综述。")
        return

    last_wf_node = "outline"
    if outline_obj:
        yield ("stage", {"name": "综述生成", "state": "active"})
        gen_ctx = format_generate_context(
            source_blocks=len(ctx.working.sources_md),
            cite_ok=cite_ok,
            failed_fetch=ctx.fetch_failed,
            fmt_label=ctx.fmt_label,
        )
        async for ev in narrate_phase_stream(
            "G",
            ctx.user_message,
            gen_ctx,
            think_acc=ctx.think_acc,
            ctx=ctx.planner_ctx,
        ):
            yield ev

        section_parts: list[tuple[Any, str]] = []
        prior = ""
        prev_node = "outline"
        gen_directives = ctx.intent.gen_directives or ""
        prior_review = ctx.store.get_latest_review(ctx.session_id)
        prior_review_text = str((prior_review or {}).get("content") or "")
        refine_plan = None
        if ctx.intent.intent == "review_refine" and prior_review_text.strip():
            refine_plan = build_section_refine_plan(
                user_message=ctx.user_message,
                outline=outline_obj,
                prior_review_text=prior_review_text,
                gen_directives=gen_directives,
            )
        section_tokens = await get_prompt_max_tokens("section_system_template")
        section_refine_tokens = await get_prompt_max_tokens("section_refine_system_template")

        for section in outline_obj.sections:
            reuse_body = ""
            if refine_plan and not refine_plan.should_regenerate(section.id):
                reuse_body = refine_plan.prior_bodies.get(section.id, "")
            if reuse_body:
                async for ev in sync_graph_node(
                    ctx.emitter,
                    ctx.graph,
                    ctx.graph_artifact_id,
                    section.id,
                    "skipped",
                    parent_id=prev_node,
                    metadata={"reused": True},
                ):
                    yield ev
                section_parts.append((section, reuse_body))
                if reuse_body.strip():
                    yield artifact_stream_delta(review_art_id, reuse_body + "\n\n")
                prior = (prior + "\n" + reuse_body)[-1500:]
                prev_node = section.id
                last_wf_node = section.id
                continue

            async for ev in sync_graph_node(
                ctx.emitter,
                ctx.graph,
                ctx.graph_artifact_id,
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
                and ctx.intent.intent == "review_refine"
            )
            sec_directives = (
                refine_plan.revision_directives if refine_plan else gen_directives
            )
            sec_tokens = section_refine_tokens if sec_is_refine else section_tokens
            try:
                async for chunk in stream_section_generate(
                    ctx.llm,
                    outline=outline_obj,
                    section=section,
                    paper_index=ctx.working.paper_index,
                    prior_excerpt=prior,
                    prior_section_body=refine_plan.prior_bodies.get(section.id, "")
                    if refine_plan
                    else "",
                    gen_directives=sec_directives,
                    writing_emphasis=ctx.planner_ctx.writing_emphasis,
                    is_refine=sec_is_refine,
                    max_tokens=sec_tokens,
                ):
                    sec_parts.append(chunk)
                    yield artifact_stream_delta(review_art_id, chunk)
            except Exception:
                _log.exception("section %s streaming failed", section.id)
            sec_body = "".join(sec_parts)
            if not sec_body.strip():
                sec_body = f"（章节「{section.title}」生成为空。）\n"
                yield artifact_stream_delta(review_art_id, sec_body)
            section_parts.append((section, sec_body))
            prior = (prior + "\n" + sec_body)[-1500:]
            async for ev in sync_graph_node(
                ctx.emitter,
                ctx.graph,
                ctx.graph_artifact_id,
                section.id,
                "done",
                parent_id=prev_node,
            ):
                yield ev
            upsert_stage(ctx.execution_trace, stage_label, "done")
            yield ("stage", {"name": stage_label, "state": "done"})
            prev_node = section.id
            last_wf_node = section.id

        raw_main = stitch_review_sections(section_parts)
        upsert_stage(ctx.execution_trace, "综述生成", "done")
        yield ("stage", {"name": "综述生成", "state": "done"})

    deliver_parent = last_wf_node

    main_text = append_compliance_footer(raw_main)
    if main_text != raw_main:
        tail = main_text[len(raw_main) :]
        if tail:
            yield artifact_stream_delta(review_art_id, tail)

    async for ev in sync_graph_node(
        ctx.emitter,
        ctx.graph,
        ctx.graph_artifact_id,
        "deliver",
        "active",
        parent_id=deliver_parent,
    ):
        yield ev

    from app.agents.review_version import (
        current_review_version_id,
        resolve_review_version_id,
    )

    session_meta = ctx.store.get_session(ctx.session_id) or {}
    version_id = resolve_review_version_id(
        meta=session_meta,
        intent=ctx.intent.intent,
        full_regen=ctx.intent.full_regen,
    )
    parent = (
        current_review_version_id(session_meta)
        if ctx.intent.intent == "review_refine" and not ctx.intent.full_regen
        else None
    )
    version_kind = "refine" if ctx.intent.intent == "review_refine" else "full"
    if ctx.intent.full_regen:
        version_kind = "full"
    _, version_id = ctx.store.save_review_artifact(
        ctx.session_id,
        main_text,
        version_id=version_id,
        version_kind=version_kind,
        parent_version=parent,
    )
    yield artifact_stream_delta(
        review_art_id,
        "",
        version_id=version_id,
        done=True,
    )
    yield (
        "literature_generate_done",
        {
            "version_id": version_id,
            "chapter_count": len(outline_obj.sections),
        },
    )

    async for ev in _stream_synthesis_matrix(ctx, context_block, parent_id=deliver_parent):
        yield ev

    async for ev in sync_graph_node(
        ctx.emitter,
        ctx.graph,
        ctx.graph_artifact_id,
        "deliver",
        "done",
        parent_id=deliver_parent,
    ):
        yield ev

    upsert_stage(ctx.execution_trace, "完成", "done")
    ctx.finalize_ctx.corpus = ctx.working
    ctx.finalize_ctx.fetch_results = ctx.fetch_results
    ctx.finalize_ctx.cite_records = ctx.cite_records
    ctx.finalize_ctx.failed_literature = ctx.failed_literature
    ctx.finalize_ctx.intent = ctx.intent
    lib_result, end_ev = await finalize_turn(
        ctx.finalize_ctx, main_text=main_text, is_review=True
    )
    yield end_ev
    yield (
        "extension",
        {"name": "library_updated", "version": "1.0", "data": lib_result},
    )
    ctx.store.patch_session_meta(ctx.session_id, {"resume_mode": None})
    yield ("stage", {"name": "完成", "state": "done"})
