from app.agents.tools.tavily_search import (
    ACADEMIC_SEARCH_DOMAINS,
    apply_literature_hit_filters,
    augment_literature_search_query,
    build_tavily_search_payload,
    filter_tavily_hits,
    normalize_tavily_results,
)


def test_build_payload_uses_academic_include_domains() -> None:
    payload = build_tavily_search_payload(
        "tvly-test",
        "multimodal llm survey",
        include_domains=ACADEMIC_SEARCH_DOMAINS,
    )

    assert payload["include_answer"] is True
    assert payload["include_raw_content"] is False
    assert "arxiv.org" in payload["include_domains"]
    assert "openreview.net" in payload["include_domains"]
    assert "scholar.google.com" not in payload["include_domains"]


def test_build_payload_always_excludes_social_noise() -> None:
    payload = build_tavily_search_payload("tvly-test", "rag papers")

    assert "include_domains" not in payload
    assert "reddit.com" in payload["exclude_domains"]
    assert "github.com" in payload["exclude_domains"]


def test_augment_query_disambiguates_manufacturing_mom() -> None:
    q = augment_literature_search_query("AI-native MOM 制造运营系统")
    assert "manufacturing operations management" in q.lower()
    assert "site:" not in q.lower()


def test_filter_tavily_hits_drops_junk() -> None:
    hits = [
        {
            "url": "https://www.reddit.com/r/PhD/comments/x",
            "title": "文献综述要被 AI 搞没了吗？ : r/PhD",
            "snippet": "",
        },
        {
            "url": "https://arxiv.org/abs/2401.00001",
            "title": "AI-native manufacturing operations management survey",
            "snippet": "",
        },
        {
            "url": "https://arxiv.org/abs/2501.00002",
            "title": "MoM: Linear Sequence Modeling with Mixture-of-Memories",
            "snippet": "",
        },
    ]
    kept = filter_tavily_hits(hits)
    assert len(kept) == 1
    assert kept[0]["url"].startswith("https://arxiv.org/abs/2401")


def test_normalize_tavily_results_keeps_snippet_short() -> None:
    data = {
        "results": [
            {
                "url": "https://arxiv.org/abs/2401.00001",
                "title": "Paper",
                "content": "x" * 1000,
            },
            {"url": "", "title": "Missing URL"},
        ]
    }

    rows = normalize_tavily_results(data)

    assert len(rows) == 1
    assert rows[0]["url"] == "https://arxiv.org/abs/2401.00001"
    assert rows[0]["title"] == "Paper"
    assert len(rows[0]["snippet"]) == 800


def test_apply_literature_hit_filters_relaxes_empty_domain_filter() -> None:
    raw = [
        {
            "url": "https://example.com/industry-mom-whitepaper",
            "title": "AI-native MOM reference architecture",
            "snippet": "",
        },
        {
            "url": "https://research.example.org/manufacturing-knowledge-graph",
            "title": "Manufacturing knowledge graph interoperability",
            "snippet": "",
        },
    ]
    hits, warning = apply_literature_hit_filters(
        raw,
        include_domains=ACADEMIC_SEARCH_DOMAINS,
        enable_junk_filter=True,
        enforce_domain_filter=True,
    )
    assert len(hits) == 2
    assert warning is not None
    assert "域名过滤" in warning
