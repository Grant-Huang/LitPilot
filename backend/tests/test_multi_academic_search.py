"""Tests for multi_academic search provider."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.tools.providers import multi_academic as ma
from app.agents.tools.web_providers import normalize_search_provider, web_search_query


@pytest.mark.asyncio
async def test_multi_academic_merges_and_dedupes(monkeypatch) -> None:
    async def fake_openalex(q, *, max_results, include_domains=None):
        return {
            "results": [
                {
                    "url": "https://arxiv.org/abs/2406.01893",
                    "title": "LLM Multi-Agent Manufacturing",
                    "snippet": "oa",
                },
            ],
        }

    monkeypatch.setattr(ma.openalex_provider, "search", fake_openalex)
    monkeypatch.setattr(
        ma.arxiv,
        "search",
        AsyncMock(
            return_value=[
                {
                    "url": "https://arxiv.org/abs/2406.01893",
                    "title": "LLM Multi-Agent Manufacturing (arXiv)",
                    "snippet": "arxiv",
                    "source": "arXiv",
                },
            ],
        ),
    )
    monkeypatch.setattr(
        ma.crossref,
        "search",
        AsyncMock(
            return_value=[
                {
                    "url": "https://doi.org/10.1000/example",
                    "title": "CrossRef hit",
                    "snippet": "cr",
                    "source": "CrossRef",
                },
            ],
        ),
    )
    monkeypatch.setattr(
        ma.pubmed,
        "search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        ma.semantic_scholar,
        "search",
        AsyncMock(return_value=[]),
    )

    out = await ma.search("multi-agent manufacturing LLM", max_results=8)
    urls = [r["url"] for r in out["results"]]
    assert len(urls) == 2
    assert "https://arxiv.org/abs/2406.01893" in urls
    assert "https://doi.org/10.1000/example" in urls
    assert out["source_counts"]["arxiv"] == 1


@pytest.mark.asyncio
async def test_multi_academic_iter_search_events(monkeypatch) -> None:
    events: list[tuple[str, dict]] = []

    async def fake_openalex(q, *, max_results, include_domains=None):
        return {"results": [{"url": "https://oa/1", "title": "t", "snippet": ""}]}

    monkeypatch.setattr(ma.openalex_provider, "search", fake_openalex)
    monkeypatch.setattr(ma.arxiv, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.crossref, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.pubmed, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.semantic_scholar, "search", AsyncMock(return_value=[]))

    async for kind, payload in ma.iter_search_events("test query", max_results=8):
        events.append((kind, payload))

    kinds = [k for k, _ in events]
    assert kinds.count("source_start") == 5
    assert kinds.count("source_done") == 5
    assert kinds[-1] == "complete"
    assert events[-1][1]["source_counts"]["openalex"] == 1


@pytest.mark.asyncio
async def test_multi_academic_emits_failed_done_for_stalled_source(monkeypatch) -> None:
    async def slow_ss(*_args, **_kwargs):
        await asyncio.sleep(3600)
        return []

    monkeypatch.setattr(ma.openalex_provider, "search", AsyncMock(return_value={"results": []}))
    monkeypatch.setattr(ma.arxiv, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.crossref, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.pubmed, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.semantic_scholar, "search", slow_ss)
    monkeypatch.setattr(ma, "SOURCE_TIMEOUTS", {"semantic_scholar": 0.2})
    monkeypatch.setattr(ma, "SOURCE_TIMEOUT_SEC", 0.5)

    events: list[tuple[str, dict]] = []
    async for kind, payload in ma.iter_search_events("stall probe", max_results=5):
        events.append((kind, payload))

    ss_done = [
        p for k, p in events if k == "source_done" and p.get("source") == "semantic_scholar"
    ]
    assert len(ss_done) == 1
    assert ss_done[0]["failed"] is True
    assert ss_done[0]["hits"] == 0


@pytest.mark.asyncio
async def test_multi_pass_emits_failed_done_on_stall(monkeypatch) -> None:
    async def slow_arxiv(*_args, **_kwargs):
        await asyncio.sleep(3600)
        return []

    monkeypatch.setattr(ma.openalex_provider, "search", AsyncMock(return_value={"results": []}))
    monkeypatch.setattr(ma.arxiv, "search", slow_arxiv)
    monkeypatch.setattr(ma.crossref, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.pubmed, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.semantic_scholar, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma, "SOURCE_TIMEOUT_SEC", 0.3)
    monkeypatch.setattr(ma, "MULTI_PASS_EVENT_POLL_SEC", 0.05)
    monkeypatch.setattr(ma, "MULTI_PASS_EXTRA_SEC", 0.1)

    specs = [
        ma.PassSpec(
            pass_index=1,
            pass_total=1,
            query="stall probe query text",
            topic_title="topic",
            max_results=5,
        ),
    ]
    events: list[tuple[str, dict]] = []
    async for kind, payload in ma.iter_multi_pass_by_source_events(specs):
        events.append((kind, payload))

    arxiv_done = [
        p for k, p in events if k == "source_done" and p.get("source") == "arxiv"
    ]
    assert len(arxiv_done) == 1
    assert arxiv_done[0]["failed"] is True


@pytest.mark.asyncio
async def test_source_coro_strips_cjk(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_oa(q, *, max_results, include_domains=None):
        captured["q"] = q
        return {"results": []}

    monkeypatch.setattr(ma.openalex_provider, "search", fake_oa)
    monkeypatch.setattr(ma.arxiv, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.crossref, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.pubmed, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(ma.semantic_scholar, "search", AsyncMock(return_value=[]))

    await ma.search("AI-native MOM 多智能体协作", max_results=5)
    assert "多智能体" not in captured.get("q", "")
    assert "AI-native" in captured.get("q", "")


@pytest.mark.asyncio
async def test_web_search_query_multi_academic_routing(monkeypatch) -> None:
    captured: dict = {}

    async def fake_ma(query, **kwargs):
        captured.update({"query": query, **kwargs})
        return {"results": [{"url": "https://arxiv.org/abs/1", "title": "t", "snippet": ""}], "answer": ""}

    monkeypatch.setattr(
        "app.agents.tools.web_providers.multi_academic_provider.search",
        fake_ma,
    )
    monkeypatch.setattr(
        "app.agents.tools.web_providers._resolve_s2_api_key",
        AsyncMock(return_value="s2-test"),
    )

    out = await web_search_query(
        "manufacturing knowledge graph",
        provider="multi_academic",
        max_results=10,
    )
    assert len(out["results"]) == 1
    assert captured.get("query") == "manufacturing knowledge graph"
    assert captured.get("s2_api_key") == "s2-test"
    assert captured.get("max_results") == 10


def test_normalize_search_provider_multi_academic() -> None:
    assert normalize_search_provider("multi_academic") == "multi_academic"


MOM_TOPIC_QUERIES = [
    (
        "方向一：AI原生MOM定义框架与参考模型",
        '"manufacturing operations management" "large language model" architecture',
    ),
    (
        "方向二：异构机器信任与制造知识图谱",
        '"industrial knowledge graph" manufacturing ontology heterogeneous',
    ),
    (
        "方向三：多智能体+知识推理+微服务整合",
        '"multi-agent" manufacturing "large language model" framework',
    ),
    (
        "方向四：传统MOM向AI原生MOM渐进式迁移",
        '"manufacturing execution system" migration microservices modernization',
    ),
]


@pytest.mark.live
@pytest.mark.asyncio
async def test_mom_four_topics_live() -> None:
    """Live probe for AI-native MOM four-aspect queries (skip if all sources empty)."""
    any_hits = 0
    for label, query in MOM_TOPIC_QUERIES:
        out = await ma.search(query, max_results=8)
        hits = out.get("results") or []
        any_hits += len(hits)
        assert isinstance(hits, list)
        for h in hits:
            assert h.get("url") and h.get("title")
    if any_hits == 0:
        pytest.skip("multi_academic returned no hits (network/rate limit)")
