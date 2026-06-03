"""Tests for literature turn finalization."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.literature_intent import LiteratureIntentResult
from app.agents.literature_turn_context import TurnFinalizeContext
from app.agents.literature_turn_finalize import finalize_turn
from app.agents.session_corpus import SessionCorpus
from app.core.think_stream import ThinkAccumulator


@pytest.mark.asyncio
async def test_finalize_turn_appends_assistant_message() -> None:
    store = MagicMock()
    corpus = SessionCorpus()
    trace: dict = {"stages": [], "tools": [], "workflows": []}
    think_acc = ThinkAccumulator()

    ctx = TurnFinalizeContext(
        store=store,
        session_id="sess-1",
        session_meta={},
        session_title="Test",
        intent=LiteratureIntentResult(intent="new_topic"),
        user_message="AI MOM survey",
        corpus=corpus,
        execution_trace=trace,
        think_acc=think_acc,
        fetch_results=[],
        cite_records=[],
        failed_literature=[],
        gen_constraints=[],
    )

    with patch(
        "app.agents.literature_turn_finalize.get_citation_format",
        new=AsyncMock(return_value="apa"),
    ):
        await finalize_turn(ctx, main_text="done")

    store.append_message.assert_called_once()
    args = store.append_message.call_args
    assert args[0][0] == "sess-1"
    assert args[0][1] == "assistant"
    assert args[0][2] == "done"
