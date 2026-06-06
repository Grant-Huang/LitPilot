from app.agents.literature_source import (
    build_fetch_hits,
    effective_merge_search_max_results,
    normalize_literature_source_mode,
    should_skip_web_search,
)


def test_normalize_mode() -> None:
    assert normalize_literature_source_mode("merge") == "merge"
    assert normalize_literature_source_mode("user_only") == "user_only"
    assert normalize_literature_source_mode("invalid") == "merge"


def test_should_skip_web_search() -> None:
    assert should_skip_web_search("user_only", ["https://a.com"])
    assert not should_skip_web_search("user_only", [])
    assert not should_skip_web_search("merge", ["https://a.com"])


def test_build_user_only() -> None:
    r = build_fetch_hits(
        "user_only",
        [{"url": "https://t.com/1", "title": "T", "snippet": ""}],
        ["https://u.com/1", "https://u.com/2"],
        max_urls=5,
    )
    assert r.skipped_web_search
    assert r.user_count == 2
    assert r.search_hit_count == 0
    assert len(r.hits) == 2
    assert r.hits[0]["url"] == "https://u.com/1"


def test_build_merge() -> None:
    tavily = [{"url": "https://t.com/1", "title": "T", "snippet": ""}]
    r = build_fetch_hits(
        "merge",
        tavily,
        ["https://u.com/1"],
        max_urls=5,
    )
    assert not r.skipped_web_search
    assert r.user_count == 1
    assert r.hits[0]["url"] == "https://u.com/1"
    assert r.hits[1]["url"] == "https://t.com/1"


def test_build_web_search_only() -> None:
    search_hits = [{"url": "https://t.com/1", "title": "T", "snippet": ""}]
    r = build_fetch_hits("merge", search_hits, [], max_urls=5)
    assert len(r.hits) == 1
    assert r.hits[0]["source"] == "web_search"


def test_effective_merge_search_max_results_lite() -> None:
    uploads = [f"https://u.com/{i}" for i in range(12)]
    assert effective_merge_search_max_results(
        40,
        source_mode="merge",
        upload_urls=uploads,
        budget="lite",
    ) == 20
    assert effective_merge_search_max_results(
        40,
        source_mode="merge",
        upload_urls=["https://u.com/1"],
        budget="lite",
    ) == 40
    assert effective_merge_search_max_results(
        40,
        source_mode="user_only",
        upload_urls=uploads,
        budget="lite",
    ) == 40
