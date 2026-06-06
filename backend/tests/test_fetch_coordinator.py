import asyncio
from unittest.mock import patch

import pytest

from app.agents.fetch_coordinator import FetchCoordinator


async def _fake_fetch(hits, **kwargs):
    await asyncio.sleep(0.01)
    return [(h, f"body-{h['url']}", None) for h in hits]


@pytest.mark.asyncio
async def test_user_urls_start_before_search_hits() -> None:
    with patch(
        "app.agents.fetch_coordinator.fetch_sources_parallel",
        side_effect=_fake_fetch,
    ):
        coord = FetchCoordinator(
            fetch_api_key=None,
            llm=None,
            parallel=2,
            timeout_sec=5.0,
            fetch_retry_count=0,
            fetch_retry_delay_ms=0,
            fetch_provider=None,
            fetch_cap=5,
            upload_urls=["https://u.com/1", "https://u.com/2"],
        )
        started = coord.start_user_urls(["https://u.com/1", "https://u.com/2"])
        assert started == 2
        assert coord.metrics.user_fetch_started_at is not None

        enqueued = coord.enqueue_search_hits(
            [
                {"url": "https://u.com/1", "title": "", "snippet": ""},
                {"url": "https://t.com/1", "title": "", "snippet": ""},
            ]
        )
        assert enqueued == 1
        assert coord.metrics.duplicate_url_skipped >= 1

        coord.mark_search_ended()
        result = await coord.finalize()
        urls = {h["url"] for h, _md, _err in result.results}
        assert "https://u.com/1" in urls
        assert "https://u.com/2" in urls
        assert "https://t.com/1" in urls


@pytest.mark.asyncio
async def test_upload_urls_reserve_fetch_budget() -> None:
    with patch(
        "app.agents.fetch_coordinator.fetch_sources_parallel",
        side_effect=_fake_fetch,
    ):
        uploads = [f"https://u.com/{i}" for i in range(5)]
        coord = FetchCoordinator(
            fetch_api_key=None,
            llm=None,
            parallel=2,
            timeout_sec=5.0,
            fetch_retry_count=0,
            fetch_retry_delay_ms=0,
            fetch_provider=None,
            fetch_cap=3,
            upload_urls=uploads,
        )
        started = coord.start_user_urls(uploads)
        assert started == 3
        assert coord.enqueue_search_hits(
            [{"url": "https://t.com/1", "title": "", "snippet": ""}]
        ) == 0

        coord.mark_search_ended()
        result = await coord.finalize()
        assert len(result.results) == 3
