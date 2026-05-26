from unittest.mock import AsyncMock, patch

import pytest

from app.agents.literature_workflow import _augment_query, _chunk_text


async def _empty_fetch_iter():
    if False:
        yield  # pragma: no cover — async generator stub


async def _mock_understanding_stream():
    from app.agents.literature_router import LiteratureRouterResult

    yield (
        "__router_result__",
        {"result": LiteratureRouterResult(session_title="t", search_query="q")},
    )


def test_augment_query_adds_sites() -> None:
    q = _augment_query("transformer survey")
    assert "arxiv" in q.lower() or "site:" in q.lower()


def test_chunk_text() -> None:
    chunks = _chunk_text("abcdefghij", size=3)
    assert "".join(chunks) == "abcdefghij"


@pytest.mark.asyncio
async def test_stream_requires_tavily_key() -> None:
    from app.agents.literature_workflow import stream_literature_turn

    with patch(
        "app.agents.literature_workflow.get_tavily_api_key",
        new_callable=AsyncMock,
        return_value="",
    ):
        events = []
        async for ev in stream_literature_turn("sess1", "test query"):
            events.append(ev)
        assert any(e[0] == "error" for e in events)


@pytest.mark.asyncio
async def test_user_only_skips_tavily(tmp_path, monkeypatch) -> None:
    from app.agents.literature_workflow import stream_literature_turn
    from app.storage.file_store import FileStore

    store = FileStore(tmp_path)
    monkeypatch.setattr(
        "app.agents.literature_workflow.get_store", lambda: store
    )
    monkeypatch.setattr(
        "app.agents.agent_settings.get_store", lambda: store
    )
    store.save_agent_settings(
        {
            "tavily_api_key": "tvly-test",
            "literature_source_mode": "user_only",
        }
    )
    meta = store.create_session("test")

    tavily_mock = AsyncMock(
        return_value={"results": [{"url": "https://t.com/x", "title": "T", "content": "s"}], "answer": "a"}
    )

    with (
        patch(
            "app.agents.literature_workflow.get_tavily_api_key",
            new_callable=AsyncMock,
            return_value="tvly-test",
        ),
        patch(
            "app.agents.literature_workflow.stream_understanding_and_route",
            return_value=_mock_understanding_stream(),
        ),
        patch(
            "app.agents.literature_workflow.cached_tavily_search",
            tavily_mock,
        ),
        patch(
            "app.agents.literature_workflow.iter_fetch_sources_parallel",
            return_value=_empty_fetch_iter(),
        ),
        patch(
            "app.agents.literature_workflow.extract_and_persist_batch",
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
            if ev[0] in ("literature_source", "error"):
                break

    tavily_mock.assert_not_called()
    source_ev = [e for e in events if e[0] == "literature_source"]
    assert source_ev
    assert source_ev[0][1]["skipped_tavily"] is True
