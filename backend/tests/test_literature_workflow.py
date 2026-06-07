from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.search_query_refiner import apply_academic_search_suffix
from app.core.think_stream import chunk_text


async def _empty_fetch_iter():
    if False:
        yield  # pragma: no cover — async generator stub


async def _mock_understanding_stream():
    from app.agents.literature_router import LiteratureRouterResult

    yield (
        "__router_result__",
        {
            "result": LiteratureRouterResult(
                session_title="Survey topic",
                search_query="survey topic academic literature review",
            )
        },
    )


def test_augment_query_adds_academic_context() -> None:
    q = apply_academic_search_suffix("transformer efficiency")
    assert "academic" in q.lower() or "survey" in q.lower()
    assert "site:" not in q.lower()


def test_chunk_text() -> None:
    chunks = chunk_text("abcdefghij", size=3)
    assert "".join(chunks) == "abcdefghij"


@pytest.mark.asyncio
async def test_stream_requires_search_api_key(tmp_path, monkeypatch) -> None:
    from app.agents.literature_turn import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr("app.agents.literature_turn.get_store", lambda: store)
    meta = store.create_session("test")

    with (
        patch(
            "app.agents.literature_turn.get_web_search_api_key",
            new_callable=AsyncMock,
            return_value="",
        ),
        patch(
            "app.agents.literature_turn.get_web_search_provider",
            new_callable=AsyncMock,
            return_value="tavily",
        ),
    ):
        events = []
        async for ev in stream_literature_turn(meta["id"], "test query"):
            events.append(ev)
        assert any(e[0] == "error" for e in events)


@pytest.mark.asyncio
async def test_user_only_skips_web_search(tmp_path, monkeypatch) -> None:
    from app.agents.literature_turn import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr(
        "app.agents.literature_turn.get_store", lambda: store
    )
    monkeypatch.setattr(
        "app.agents.agent_settings.get_store", lambda: store
    )
    store.save_agent_settings(
        {
            "web_search_api_key": "tvly-test",
            "literature_source_mode": "user_only",
        }
    )
    caps = store.list_system_capabilities()
    for cap in caps:
        if cap.get("capability_id") == "literature_source":
            cap.setdefault("params", {})["literature_source_mode"] = "user_only"
        if cap.get("capability_id") == "web_search":
            cap.setdefault("params", {})["search_provider"] = "tavily"
    store.save_system_capabilities(caps)
    meta = store.create_session("test")

    search_mock = AsyncMock(
        return_value={"results": [{"url": "https://t.com/x", "title": "T", "content": "s"}], "answer": "a"}
    )

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content=""))

    with (
        patch(
            "app.agents.literature_turn.get_review_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_planner_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_pipeline_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_assessor_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_web_search_api_key",
            new_callable=AsyncMock,
            return_value="tvly-test",
        ),
        patch(
            "app.agents.literature_turn.assess_first_turn_gate",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch(
            "app.agents.literature_turn.resolve_outline_plan",
            return_value=(False, None, []),
        ),
        patch(
            "app.agents.literature_turn.stream_understanding_and_route",
            return_value=_mock_understanding_stream(),
        ),
        patch(
            "app.agents.literature_phases.cached_web_search",
            search_mock,
        ),
        patch(
            "app.agents.literature_phases.iter_fetch_sources_parallel",
            return_value=_empty_fetch_iter(),
        ),
        patch(
            "app.agents.literature_phases.extract_and_persist_batch",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        events = []
        async for ev in stream_literature_turn(
            meta["id"],
            "survey topic",
            extra_fetch_urls=["https://user.example/paper"],
        ):
            events.append(ev)

    search_mock.assert_not_called()
    source_ev = [e for e in events if e[0] == "literature_source"]
    assert source_ev, f"events={[e[0] for e in events]}"
    assert source_ev[0][1]["skipped_web_search"] is True


@pytest.mark.asyncio
async def test_understanding_stage_emitted_before_intent_routing(
    tmp_path, monkeypatch
) -> None:
    """首屏反馈：理解阶段应在意图路由/workflow 图之前立刻出现。"""
    from app.agents.literature_turn import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr("app.agents.literature_turn.get_store", lambda: store)
    monkeypatch.setattr("app.agents.agent_settings.get_store", lambda: store)
    store.save_agent_settings({"web_search_api_key": "tvly-test"})
    meta = store.create_session("wf-order")

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content=""))

    with (
        patch(
            "app.agents.literature_turn.get_review_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_planner_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_pipeline_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_assessor_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_turn.get_web_search_api_key",
            new_callable=AsyncMock,
            return_value="tvly-test",
        ),
        patch(
            "app.agents.literature_turn.stream_understanding_and_route",
            return_value=_mock_understanding_stream(),
        ),
        patch(
            "app.agents.literature_turn.assess_first_turn_gate",
            new_callable=AsyncMock,
            return_value=(None, None),
        ),
        patch(
            "app.agents.literature_turn.resolve_outline_plan",
            return_value=(False, None, []),
        ),
        patch(
            "app.agents.literature_turn.run_retrieval_pipeline",
            return_value=_empty_fetch_iter(),
        ),
    ):
        events = []
        async for ev in stream_literature_turn(meta["id"], "survey topic"):
            events.append(ev)
            if ev[0] == "artifact" and ev[1].get("lang") == "workflow-graph":
                break

    understand_idx = next(
        (
            i
            for i, e in enumerate(events)
            if e[0] == "stage" and e[1].get("name") == "理解研究问题"
        ),
        None,
    )
    wf_idx = next(
        (
            i
            for i, e in enumerate(events)
            if e[0] == "artifact" and e[1].get("lang") == "workflow-graph"
        ),
        None,
    )
    turn_start_idx = next(
        (i for i, e in enumerate(events) if e[0] == "extension" and e[1].get("name") == "turn_start"),
        None,
    )
    assert understand_idx is not None
    assert turn_start_idx is not None
    assert understand_idx < 8
    assert turn_start_idx < understand_idx
    assert wf_idx is not None
    assert understand_idx < wf_idx
