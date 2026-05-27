from app.agents.tools.tavily_search import (
    ACADEMIC_SEARCH_DOMAINS,
    build_tavily_search_payload,
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


def test_build_payload_omits_empty_domain_filters() -> None:
    payload = build_tavily_search_payload("tvly-test", "rag papers")

    assert "include_domains" not in payload
    assert "exclude_domains" not in payload


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
