from app.agents.literature_source import (
    build_fetch_hits,
    normalize_literature_source_mode,
    should_skip_tavily,
)


def test_normalize_mode() -> None:
    assert normalize_literature_source_mode("merge") == "merge"
    assert normalize_literature_source_mode("user_only") == "user_only"
    assert normalize_literature_source_mode("invalid") == "merge"


def test_should_skip_tavily() -> None:
    assert should_skip_tavily("user_only", ["https://a.com"])
    assert not should_skip_tavily("user_only", [])
    assert not should_skip_tavily("merge", ["https://a.com"])


def test_build_user_only() -> None:
    r = build_fetch_hits(
        "user_only",
        [{"url": "https://t.com/1", "title": "T", "snippet": ""}],
        ["https://u.com/1", "https://u.com/2"],
        max_urls=5,
    )
    assert r.skipped_tavily
    assert r.user_count == 2
    assert r.tavily_count == 0
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
    assert not r.skipped_tavily
    assert r.user_count == 1
    assert r.hits[0]["url"] == "https://u.com/1"
    assert r.hits[1]["url"] == "https://t.com/1"


def test_build_tavily_only() -> None:
    tavily = [{"url": "https://t.com/1", "title": "T", "snippet": ""}]
    r = build_fetch_hits("merge", tavily, [], max_urls=5)
    assert len(r.hits) == 1
    assert r.hits[0]["source"] == "tavily"
