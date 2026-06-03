"""Turn finalization: corpus/meta/library persistence and clarification pauses."""
from __future__ import annotations

from typing import Any, AsyncIterator

from app.agents.agent_settings import get_citation_format
from app.agents.execution_trace import upsert_stage
from app.agents.literature_clarification import ClarificationGate, format_gate_message
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.session_corpus import save_session_corpus
from app.library.from_run import upsert_library_from_run


async def finalize_turn(
    ctx: TurnFinalizeContext,
    *,
    main_text: str,
    is_review: bool = False,
) -> dict[str, Any]:
    save_session_corpus(ctx.store, ctx.session_id, ctx.corpus)

    patch: dict[str, Any] = {
        "gen_constraints": ctx.gen_constraints,
        "last_intent": ctx.intent.intent,
        "last_failed_literature": ctx.failed_literature,
    }
    if not ctx.session_meta.get("initial_query") and ctx.intent.intent == "new_topic":
        patch["initial_query"] = ctx.user_message.strip()
    ctx.store.patch_session_meta(ctx.session_id, patch)

    lib_result: dict[str, Any] = {"added": 0, "merged": 0, "item_ids": [], "total": 0}
    if ctx.fetch_results or ctx.cite_records:
        lib_result = upsert_library_from_run(
            ctx.session_id,
            fetch_results=ctx.fetch_results,
            cite_records=ctx.cite_records,
            failed_literature=ctx.failed_literature,
            review_text=main_text if is_review else "",
            citation_format=await get_citation_format(),
            session_title=ctx.session_title,
        )

    think_text = ctx.think_acc.finalize()
    if think_text:
        ctx.execution_trace["thinkContent"] = think_text

    msg_meta: dict[str, Any] = {
        "execution_trace": ctx.execution_trace,
        "intent": ctx.intent.intent,
    }
    if think_text:
        msg_meta["think"] = think_text
    if ctx.failed_literature:
        msg_meta["failed_literature"] = ctx.failed_literature
    msg_meta["library_item_ids"] = lib_result.get("item_ids") or []
    ctx.store.append_message(ctx.session_id, "assistant", main_text, meta=msg_meta)
    return lib_result


async def yield_clarification_pause(
    gate: ClarificationGate,
    ctx: TurnFinalizeContext,
    *,
    gate_resolved: dict[str, bool],
    resume_mode: str | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    if ctx.corpus.fetch_hits or ctx.corpus.sources_md:
        save_session_corpus(ctx.store, ctx.session_id, ctx.corpus)
    msg = format_gate_message(gate)
    yield ("literature_clarification", gate.to_sse_payload())
    yield ("text", {"delta": msg})
    meta_patch: dict[str, Any] = {
        "pending_gate": gate.to_dict(),
        "gate_resolved": dict(gate_resolved),
    }
    if resume_mode:
        meta_patch["resume_mode"] = resume_mode
    ctx.store.patch_session_meta(ctx.session_id, meta_patch)
    upsert_stage(ctx.execution_trace, "等待澄清", "done")
    yield ("stage", {"name": "等待澄清", "state": "done"})
    await finalize_turn(ctx, main_text=msg)
    yield ("stage", {"name": "完成", "state": "done"})
