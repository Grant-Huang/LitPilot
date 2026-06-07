from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.search_query_refiner import apply_academic_search_suffix
from app.core.think_stream import chunk_text


async def _empty_pipeline():
    from app.agents.literature_turn_pipeline import RetrievalPipelineContext

    if False:
        yield  # pragma: no cover


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
    monkeypatch.setattr("app.agents.agent_settings.get_store", lambda: store)
    monkeypatch.setattr("app.storage.file_store.get_store", lambda: store)
    meta = store.create_session("test")

    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value=MagicMock(content=""))

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
        patch(
            "app.agents.literature_intent.get_router_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_intent.list_session_library_items",
            return_value=[],
        ),
        patch(
            "app.agents.literature_turn.resolve_session_corpus",
            return_value=None,
        ),
    ):
        events = []
        async for ev in stream_literature_turn(meta["id"], "test query"):
            events.append(ev)
        assert any(e[0] == "error" for e in events)


@pytest.mark.asyncio
async def test_v2_event_order_turn_start_intent_then_understanding(
    tmp_path, monkeypatch
) -> None:
    from app.agents.literature_turn import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr("app.agents.literature_turn.get_store", lambda: store)
    monkeypatch.setattr("app.agents.agent_settings.get_store", lambda: store)
    monkeypatch.setattr("app.storage.file_store.get_store", lambda: store)
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
            "app.agents.literature_intent.get_router_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.agents.literature_router.route_literature",
            new_callable=AsyncMock,
            return_value=MagicMock(
                session_title="Survey topic",
                search_query="survey topic academic",
            ),
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
            "app.agents.literature_turn.run_retrieval_pipeline",
            return_value=_empty_pipeline(),
        ),
        patch(
            "app.agents.literature_turn.resolve_session_corpus",
            return_value=None,
        ),
        patch(
            "app.agents.literature_intent.list_session_library_items",
            return_value=[],
        ),
    ):
        events = []
        async for ev in stream_literature_turn(meta["id"], "survey topic"):
            events.append(ev)
            if ev[0] == "stage" and ev[1].get("name") == "理解研究问题":
                break

    understand_idx = next(
        (
            i
            for i, e in enumerate(events)
            if e[0] == "stage" and e[1].get("name") == "理解研究问题"
        ),
        None,
    )
    turn_start_idx = next(
        (
            i
            for i, e in enumerate(events)
            if e[0] == "extension" and e[1].get("name") == "turn_start"
        ),
        None,
    )
    intent_idx = next(
        (i for i, e in enumerate(events) if e[0] == "literature_intent"),
        None,
    )
    assert understand_idx is not None
    assert turn_start_idx is not None
    assert intent_idx is not None
    assert turn_start_idx < intent_idx < understand_idx
