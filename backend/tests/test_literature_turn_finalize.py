from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import _combine_assistant_text


def test_combine_assistant_text_prefix_and_body() -> None:
    ctx = TurnFinalizeContext(
        store=None,
        session_id="s",
        session_meta={},
        session_title="",
        intent=None,  # type: ignore[arg-type]
        user_message="",
        corpus=None,  # type: ignore[arg-type]
        execution_trace={},
        think_acc=None,  # type: ignore[arg-type]
        fetch_results=[],
        cite_records=[],
        failed_literature=[],
        gen_constraints=[],
        assistant_prefix="**已理解你的研究需求**\n\n1. RQ1\n\n---",
    )
    out = _combine_assistant_text(ctx, "综述正文…")
    assert out.startswith("**已理解你的研究需求**")
    assert "综述正文" in out
