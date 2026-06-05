import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.literature_planner import (
    FetchNarrationThrottle,
    PlannerContext,
    _extract_router_from_text,
    format_fetch_progress_context,
    format_search_before_context,
    should_narrate,
    stream_understanding_and_route,
)
from app.core.think_stream import SYS_END, SYS_START, wrap_system_line


def test_should_narrate_lite_checkpoints() -> None:
    ctx = PlannerContext(True, "lite", False, 280)
    assert should_narrate("A", ctx)
    assert should_narrate("C", ctx)
    assert should_narrate("E", ctx)
    assert not should_narrate("B", ctx)


def test_should_narrate_off() -> None:
    ctx = PlannerContext(True, "off", False, 280)
    assert not should_narrate("A", ctx)


def test_should_narrate_full_checkpoints() -> None:
    ctx = PlannerContext(True, "full", False, 280)
    for cp in ("A", "B", "C", "D", "E", "F", "G"):
        assert should_narrate(cp, ctx)


def test_fetch_narration_throttle_every_n() -> None:
    t = FetchNarrationThrottle(every_n=3, interval_sec=999.0)
    assert not t.note_completed()
    assert not t.note_completed()
    assert t.note_completed()
    t.mark_narrated()
    assert not t.note_completed()


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


def test_extract_router_from_text() -> None:
    raw = (
        "将围绕 AI-Native MES 检索。\n"
        '{"session_title":"AI原生制造执行","search_query":"AI-native MES survey"}'
    )
    r = _extract_router_from_text(raw, "AI-Native MES")
    assert r.session_title == "AI原生制造执行"
    assert "MES" in r.search_query


def test_wrap_system_line() -> None:
    w = wrap_system_line("已跳过 web_search")
    assert w.startswith(SYS_START)
    assert w.endswith(SYS_END + "\n")


@pytest.mark.asyncio
async def test_stream_understanding_refines_truncated_orchestrator_output() -> None:
    long_q = (
        "I want a literature review on AI-native MOM covering four aspects: "
        "definitions, trust, multi-agent systems, and migration paths."
    )

    async def fake_stream(*_args, **_kwargs):
        yield ("think", {"delta": "reasoning only", "source": "model"})
        yield ("think", {"delta": "", "done": True})

    mock_llm = MagicMock()
    mock_llm.chat_stream_parts = fake_stream
    mock_llm.chat = AsyncMock(
        return_value=MagicMock(
            content=(
                '{"session_title":"AI-native MOM review",'
                '"search_query":"AI-native MOM survey"}'
            ),
        ),
    )

    with (
        patch(
            "app.agents.literature_planner.get_planner_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_router.get_planner_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
    ):
        events = [
            ev
            async for ev in stream_understanding_and_route(
                long_q,
                ctx=PlannerContext(True, "lite", False, 280),
            )
        ]

    router = next(ev[1]["result"] for ev in events if ev[0] == "__router_result__")
    assert router.session_title == "AI-native MOM review"
    mock_llm.chat.assert_awaited_once()
