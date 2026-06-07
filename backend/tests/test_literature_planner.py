import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.literature_planner import (
    PlannerContext,
    _extract_router_from_text,
    format_fetch_progress_context,
    format_search_before_context,
    should_narrate,
    stream_understanding_and_route,
)
from app.core.think_stream import SYS_END, SYS_START, wrap_system_line


def test_should_narrate_lite_checkpoints() -> None:
    ctx = PlannerContext(True, False, 280)
    assert should_narrate("C", ctx)
    assert should_narrate("E", ctx)
    assert not should_narrate("F2", ctx)
    assert not should_narrate("A", ctx)
    assert not should_narrate("B", ctx)


def test_should_narrate_disabled_without_planner() -> None:
    ctx = PlannerContext(False, False, 280)
    assert not should_narrate("C", ctx)



def test_format_search_before_context() -> None:
    text = format_search_before_context(
        query="AI MES",
        source_mode="merge",
        search_max_results=10,
        upload_count=2,
        skipped_web_search=False,
    )
    assert "AI MES" in text
    assert "merge" in text


def test_format_fetch_progress_context() -> None:
    text = format_fetch_progress_context(
        total=20,
        completed=5,
        ok=4,
        failed=1,
        recent_labels=["paper a"],
    )
    assert "5/20" in text
    assert "paper a" in text


def test_extract_router_from_text_with_search_aspects() -> None:
    raw = (
        "将围绕 AI-Native MES 检索。\n"
        + json.dumps(
            {
                "session_title": "AI原生制造执行",
                "search_query": "AI-native MES survey",
                "search_aspects": [
                    {
                        "aspect_id": 1,
                        "aspect_label": "定义",
                        "arxiv_query": "AI-native MES manufacturing survey",
                    }
                ],
            },
            ensure_ascii=False,
        )
    )
    r = _extract_router_from_text(raw, "AI-Native MES")
    assert r.session_title == "AI原生制造执行"
    assert len(r.search_aspects) == 1


def test_wrap_system_line() -> None:
    w = wrap_system_line("已跳过 web_search")
    assert w.startswith(SYS_START)
    assert w.endswith(SYS_END + "\n")


@pytest.mark.asyncio
async def test_stream_understanding_falls_back_to_truncation_when_no_json() -> None:
    """When Checkpoint A produces no JSON, _extract_router_from_text returns a
    truncated fallback title.  Previously refine_router_session_title would call
    router LLM again; now the truncation is accepted and resolve_auto_session_title
    at the turn level handles any needed refinement."""
    long_q = (
        "I want a literature review on AI-native MOM covering four aspects: "
        "definitions, trust, multi-agent systems, and migration paths."
    )

    async def fake_stream(*_args, **_kwargs):
        yield ("think", {"delta": "reasoning only", "source": "model"})
        yield ("think", {"delta": "", "done": True})

    mock_llm = MagicMock()
    mock_llm.chat_stream_parts = fake_stream

    with (
        patch(
            "app.agents.literature_planner.get_planner_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_planner.get_understanding_system_prompt",
            new_callable=AsyncMock,
            return_value="understanding system",
        ),
        patch(
            "app.agents.literature_planner.get_prompt_max_tokens",
            new_callable=AsyncMock,
            return_value=1200,
        ),
    ):
        events = [
            ev
            async for ev in stream_understanding_and_route(
                long_q,
                ctx=PlannerContext(True, False, 280),
            )
        ]

    router = next(ev[1]["result"] for ev in events if ev[0] == "__router_result__")
    # No JSON means title is the 40-char message truncation fallback
    assert router.session_title == long_q[:40] + "…"
    # Router LLM is not called — refinement is now handled at turn level
    mock_llm.chat.assert_not_called()
