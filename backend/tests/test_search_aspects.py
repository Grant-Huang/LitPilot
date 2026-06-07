"""Tests for search aspect planning and default exclusions."""
from __future__ import annotations

import json

from app.agents.literature_router import build_router_result
from app.agents.search_aspects import (
    DEFAULT_SEARCH_EXCLUDE_TERMS,
    SearchAspect,
    aspects_to_sub_topics,
    collect_search_exclusions,
    parse_search_aspects,
    query_for_source,
    sub_topic_pass_spec,
)
from app.agents.tools.search_hits import filter_search_hits
from app.schemas.literature_outline import ResearchSubTopic


def test_parse_search_aspects_from_router_json() -> None:
    raw = [
        {
            "aspect_id": 1,
            "aspect_label": "制造知识图谱",
            "core_concepts": ["MOM", "knowledge graph"],
            "arxiv_query": "manufacturing knowledge graph MOM survey",
            "semantic_scholar_query": "manufacturing knowledge graph trust",
            "openalex_crossref_query": '"manufacturing operations" knowledge graph',
            "pubmed_query": "",
            "exclude_terms": ["municipal"],
        }
    ]
    aspects = parse_search_aspects(raw)
    assert len(aspects) == 1
    assert aspects[0].skip_sources() == frozenset({"pubmed"})
    sq = aspects[0].source_queries()
    assert "arxiv" in sq
    assert "pubmed" not in sq


def test_build_router_result_parses_search_aspects() -> None:
    data = {
        "session_title": "AI 制造 MOM",
        "search_query": "",
        "search_aspects": [
            {
                "aspect_id": 1,
                "aspect_label": "定义框架",
                "arxiv_query": "AI-native MOM reference model manufacturing",
                "openalex_crossref_query": "AI-native manufacturing operations management",
            }
        ],
    }
    result = build_router_result(data, "AI-native MOM brief")
    assert len(result.search_aspects) == 1
    assert result.search_query


def test_aspects_to_sub_topics_carries_source_queries() -> None:
    aspect = SearchAspect(
        aspect_id=1,
        aspect_label="信任机制",
        arxiv_query="heterogeneous machine trust manufacturing",
        openalex_crossref_query="machine trust manufacturing knowledge graph",
    )
    topics = aspects_to_sub_topics([aspect])
    assert len(topics) == 1
    assert topics[0].source_queries.get("arxiv")


def test_default_exclusions_filter_municipal_and_peer_review() -> None:
    hits = [
        {
            "url": "https://doi.org/10.1/muni",
            "title": "面向韧性城市的市政工程项目咨询知识图谱构建",
        },
        {
            "url": "https://arxiv.org/abs/2001.10617",
            "title": "Systematic Review of Approaches to Improve Peer Assessment at Scale",
        },
        {
            "url": "https://arxiv.org/abs/2301.04999",
            "title": "AI-native MOM reference architecture manufacturing",
        },
    ]
    kept = filter_search_hits(hits)
    titles = [h["title"] for h in kept]
    assert "AI-native MOM reference architecture manufacturing" in titles
    assert not any("市政" in t for t in titles)
    assert not any("Peer Assessment" in t for t in titles)


def test_collect_search_exclusions_merges_defaults_and_aspect_terms() -> None:
    aspect = SearchAspect(aspect_id=1, aspect_label="x", exclude_terms=["custom noise"])
    out = collect_search_exclusions([aspect])
    assert "municipal" in out
    assert "custom noise" in out
    assert "municipal" in DEFAULT_SEARCH_EXCLUDE_TERMS


def test_query_for_source_prefers_per_source_map() -> None:
    q = query_for_source(
        "arxiv",
        source_queries={"arxiv": "MOM manufacturing survey", "crossref": "other"},
        fallback="fallback query",
    )
    assert "MOM" in q


def test_sub_topic_pass_spec_skips_empty_pubmed() -> None:
    st = ResearchSubTopic(
        id="t1",
        title="KG",
        description="",
        search_query="manufacturing knowledge graph",
        source_queries={"arxiv": "manufacturing KG", "crossref": "manufacturing KG"},
    )
    _, sq, skip = sub_topic_pass_spec(st)
    assert "pubmed" in skip
    assert sq["arxiv"]
