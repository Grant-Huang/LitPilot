"""arXiv provider retry tests."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.agents.tools.providers.academic import arxiv


@pytest.mark.asyncio
async def test_arxiv_retries_on_429(monkeypatch) -> None:
    calls = {"n": 0}
    ok_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Test Paper</title>
    <summary>abstract</summary>
    <published>2024-01-01T00:00:00Z</published>
    <author><name>A Author</name></author>
  </entry>
</feed>"""

    class FakeResponse:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text
            self.headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "error",
                    request=httpx.Request("GET", arxiv.API_BASE),
                    response=httpx.Response(self.status_code),
                )

    class FakeClient:
        async def get(self, *_args, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResponse(429)
            return FakeResponse(200, ok_xml)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(arxiv.httpx, "AsyncClient", lambda **_kw: FakeClient())
    monkeypatch.setattr(arxiv, "wait_after_429", AsyncMock(return_value=0.0))
    monkeypatch.setattr(arxiv, "pace_before_request", AsyncMock(return_value=None))

    rows = await arxiv.search("LLM test", limit=5, min_year=2019, categories="")
    assert calls["n"] == 2
    assert len(rows) == 1
    assert rows[0]["url"] == "https://arxiv.org/abs/2401.00001"
