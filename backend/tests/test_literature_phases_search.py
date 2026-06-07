"""Multi-pass literature search merge and zero-hit gate."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.literature_phases import stream_expanded_search_phase
from app.agents.session_corpus import SessionCorpus
from app.core.think_stream import ThinkAccumulator
from app.library.canonical import canonical_key


def _fake_search_result(
    n: int,
    *,
    answer: str = "",
    url_prefix: str = "https://arxiv.org/abs/2401.0",
) -> dict:
    return {
        "results": [
            {
                "url": f"{url_prefix}{i:02d}",
                "title": f"Paper {i}",
                "content": f"snippet {i}",
            }
            for i in range(n)
        ],
        "answer": answer,
    }


async def _empty_narrate(*_args, **_kwargs):
    return
    yield  # pragma: no cover — async generator


@pytest.mark.asyncio
async def test_expanded_search_does_not_abort_when_last_pass_empty() -> None:
    """第 4/4 轮 0 命中时，前几轮命中仍应合并成功。"""
    responses = [
        _fake_search_result(4, answer="ans1", url_prefix="https://arxiv.org/abs/2401.0"),
        _fake_search_result(5, answer="ans2", url_prefix="https://arxiv.org/abs/2402.0"),
        _fake_search_result(5, answer="ans3", url_prefix="https://arxiv.org/abs/2403.0"),
        _fake_search_result(0, url_prefix="https://arxiv.org/abs/2404.0"),
    ]
    mock_search = AsyncMock(side_effect=responses)
    out: dict = {}
    events: list[tuple[str, dict]] = []
    think_acc = ThinkAccumulator()
    execution_trace: dict = {}

    with (
        patch("app.agents.literature_phases.cached_web_search", mock_search),
        patch("app.agents.literature_phases.narrate_phase_stream", _empty_narrate),
    ):
        async for ev in stream_expanded_search_phase(
            user_message="AI-native MOM review",
            queries=["q1", "q2", "q3", "q4"],
            search_api_key="tvly-test",
            search_max_results=20,
            search_retry_count=0,
            fetch_retry_delay_ms=0,
            source_mode="merge",
            upload_count=0,
            skip_web_search=False,
            upload_urls=[],
            think_acc=think_acc,
            planner_ctx=None,
            execution_trace=execution_trace,
            result=out,
            search_provider="tavily",
        ):
            events.append(ev)

    assert len(out.get("hits") or []) > 0
    merge_ev = next(e for e in events if e[0] == "literature_search_merge")
    assert merge_ev[1]["raw_total"] == 14
    assert merge_ev[1]["deduped"] == 14
    assert merge_ev[1]["pass_hit_counts"] == [4, 5, 5, 0]
    assert merge_ev[1]["tool_hit_total"] == 14
    weak = merge_ev[1].get("weak_subtopics") or []
    assert len(weak) == 1
    assert weak[0]["pass_index"] == 4
    assert weak[0]["hits_taken"] == 0
    persisted = execution_trace.get("literatureStats", {}).get("weakSubtopics") or []
    assert persisted[0]["passIndex"] == 4
    assert persisted[0]["hitsTaken"] == 0


async def _narrate_fail_on_phase_c(phase: str, *args, **kwargs):
    if phase == "C":
        raise RuntimeError("narrate failed")
    if False:
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_search_phase_keeps_hits_when_narrate_fails() -> None:
    """pass_out 在 narrate 之前写入，避免解说失败导致命中丢失。"""
    from app.agents.literature_phases import stream_search_phase

    mock_search = AsyncMock(return_value=_fake_search_result(3, answer="brief"))
    pass_out: dict = {}
    think_acc = ThinkAccumulator()

    with (
        patch("app.agents.literature_phases.cached_web_search", mock_search),
        patch(
            "app.agents.literature_phases.narrate_phase_stream",
            side_effect=_narrate_fail_on_phase_c,
        ),
    ):
        with pytest.raises(RuntimeError, match="narrate failed"):
            async for _ev in stream_search_phase(
                user_message="topic",
                query="q",
                search_api_key="tvly-test",
                search_max_results=8,
                search_retry_count=0,
                fetch_retry_delay_ms=0,
                source_mode="merge",
                upload_count=0,
                skip_web_search=False,
                upload_urls=[],
                think_acc=think_acc,
                planner_ctx=None,
                execution_trace={},
                result=pass_out,
                pass_index=1,
                pass_total=1,
                search_provider="tavily",
            ):
                pass

    assert len(pass_out.get("hits") or []) == 3


@pytest.mark.asyncio
async def test_expanded_search_all_corpus_dupes_does_not_raise() -> None:
    """命中均为已收录 URL 时不应误报「未检索到可用文献」。"""
    url = "https://arxiv.org/abs/2401.0000"
    corpus = SessionCorpus()
    corpus.fetch_hits = [{"url": url, "title": "Existing", "snippet": ""}]
    corpus.register_url(url)
    mock_search = AsyncMock(
        return_value={
            "results": [{"url": url, "title": "Paper", "content": "snippet"}],
            "answer": "",
        },
    )
    out: dict = {}
    think_acc = ThinkAccumulator()

    with (
        patch("app.agents.literature_phases.cached_web_search", mock_search),
        patch("app.agents.literature_phases.narrate_phase_stream", _empty_narrate),
    ):
        async for _ev in stream_expanded_search_phase(
            user_message="topic",
            queries=["q1", "q2"],
            search_api_key="tvly-test",
            search_max_results=10,
            search_retry_count=0,
            fetch_retry_delay_ms=0,
            source_mode="merge",
            upload_count=0,
            skip_web_search=False,
            upload_urls=[],
            think_acc=think_acc,
            planner_ctx=None,
            execution_trace={},
            corpus=corpus,
            result=out,
            search_provider="tavily",
        ):
            pass

    assert out.get("hits") == []


@pytest.mark.asyncio
async def test_single_search_emits_pass_hits_for_pipeline() -> None:
    """单 query 检索完成后应 yield pass_hits，供流水线 fetch 消费。"""
    from app.agents.literature_phases import stream_search_phase

    async def _empty_narrate(*_args, **_kwargs):
        return
        yield  # pragma: no cover — async generator

    mock_search = AsyncMock(return_value=_fake_search_result(3))
    events: list[tuple[str, dict]] = []
    think_acc = ThinkAccumulator()

    with patch("app.agents.literature_phases.cached_web_search", mock_search):
        with patch("app.agents.literature_phases.narrate_phase_stream", _empty_narrate):
            async for ev in stream_search_phase(
                user_message="topic",
                query="AI-native MOM survey",
                search_api_key="",
                search_max_results=8,
                search_retry_count=0,
                fetch_retry_delay_ms=0,
                source_mode="merge",
                upload_count=0,
                skip_web_search=False,
                upload_urls=[],
                think_acc=think_acc,
                planner_ctx=None,
                execution_trace={},
                emit_pass_hits=True,
                search_provider="tavily",
            ):
                events.append(ev)

    pass_hits = [ev for ev in events if ev[0] == "literature_search_pass_hits"]
    assert len(pass_hits) == 1
    assert len(pass_hits[0][1].get("hits") or []) == 3
    assert pass_hits[0][1].get("pass_total") == 1
