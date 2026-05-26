from app.agents.url_list import (
    merge_fetch_hits,
    parse_url_list_file,
    sanitize_fetch_urls,
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
