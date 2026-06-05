from app.agents.url_list import (
    display_title_from_url,
    merge_fetch_hits,
    parse_url_list_file,
    resolve_fetch_display_title,
    sanitize_fetch_urls,
    title_from_search_hit,
)


def test_parse_txt_lines() -> None:
    text = "# refs\nhttps://arxiv.org/abs/123\nhttps://doi.org/10.1/xyz\n"
    urls = parse_url_list_file(text, filename="refs.txt")
    assert len(urls) == 2
    assert urls[0].startswith("https://arxiv.org")


def test_parse_csv() -> None:
    text = "title,url\nA,https://example.com/a\n"
    urls = parse_url_list_file(text, filename="list.csv")
    assert urls == ["https://example.com/a"]


def test_merge_prioritizes_upload() -> None:
    tavily = [{"url": "https://t.com/1", "title": "T", "snippet": ""}]
    extra = ["https://u.com/1", "https://u.com/2"]
    merged, n = merge_fetch_hits(tavily, extra, max_urls=5)
    assert n == 2
    assert merged[0]["url"] == "https://u.com/1"
    assert merged[1]["url"] == "https://u.com/2"
    assert merged[2]["url"] == "https://t.com/1"


def test_sanitize_caps() -> None:
    raw = [f"https://example.com/{i}" for i in range(30)]
    assert len(sanitize_fetch_urls(raw, max_items=20)) == 20


def test_resolve_fetch_display_title_from_ctx_md() -> None:
    hit = {"url": "https://example.com/p", "title": "", "snippet": ""}
    ctx = "## [网页材料] Real Article Title\n\nbody"
    assert resolve_fetch_display_title(hit, ctx) == "Real Article Title"


def test_resolve_fetch_display_title_prefers_hit_title() -> None:
    hit = {
        "url": "https://example.com/p",
        "title": "From web_search",
        "snippet": "short",
    }
    assert resolve_fetch_display_title(hit, "") == "From web_search"


def test_display_title_from_semantic_scholar_url() -> None:
    url = (
        "https://www.semanticscholar.org/paper/"
        "Agentic-AI-Frameworks-in-SMMEs-A-Systematic-Review/"
        "423706ce66f4d5fc20de13852410d99b7a403e98"
    )
    title = display_title_from_url(url)
    assert "423706ce" not in title
    assert "Agentic" in title or "SMMEs" in title


def test_title_from_search_hit_uses_snippet_not_hash() -> None:
    hit = {
        "url": "https://www.semanticscholar.org/paper/X/y/abcdef0123456789abcdef0123456789abcdef01",
        "title": "",
        "snippet": "Evaluating Agentic AI Systems in Manufacturing",
    }
    assert "Evaluating Agentic" in title_from_search_hit(hit)


def test_resolve_fetch_display_title_snippet_fallback() -> None:
    hit = {
        "url": "https://example.com/p",
        "title": "",
        "snippet": "A long enough snippet line for display",
    }
    assert (
        resolve_fetch_display_title(hit, "")
        == "A long enough snippet line for display"
    )
