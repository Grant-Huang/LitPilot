import pytest

from app.agents.tools.providers.native_fetch import (
    fetch_bytes,
    permitted_redirect,
    pick_ojs_pdf_url,
)
from app.agents.tools.providers.native_search import search as native_search
from app.agents.tools.providers.openalex import _work_url, search as openalex_search
from app.agents.tools.pdf_text import (
    normalize_pdf_extract_backend,
    pdf_bytes_to_text,
)
from app.agents.tools.source_resolve import (
    extract_citation_pdf_url,
    extract_pdfjs_embedded_url,
    resolve_landing_page_to_pdf_url,
    resolve_semantic_scholar_fetch_url,
    semantic_scholar_paper_id,
)
from app.agents.tools.providers import native_search as native_search_provider
from app.agents.tools.web_providers import (
    normalize_fetch_provider,
    normalize_search_provider,
    web_search_query,
)
from app.agents.tools.web_search_domains import (
    filter_hits_by_domains,
    validate_search_domains,
)


def test_normalize_pdf_extract_backend() -> None:
    assert normalize_pdf_extract_backend("pypdf") == "pypdf"
    assert normalize_pdf_extract_backend("pymupdf4llm") == "pymupdf4llm"
    assert normalize_pdf_extract_backend(None) == "pymupdf4llm"
    assert normalize_pdf_extract_backend("unknown") == "pypdf"


def test_pdf_bytes_to_text_pypdf_minimal() -> None:
    # Not a valid PDF — should return empty
    assert pdf_bytes_to_text(b"not pdf", backend="pypdf") == ""


def test_normalize_providers() -> None:
    assert normalize_fetch_provider("native") == "native"
    assert normalize_fetch_provider("unknown") == "native"
    assert normalize_search_provider("multi_academic") == "multi_academic"
    assert normalize_search_provider("native") == "native"
    assert normalize_search_provider("brave") == "brave"
    assert normalize_search_provider("") == "multi_academic"


def test_validate_search_domains_xor() -> None:
    assert validate_search_domains(["arxiv.org"], ["reddit.com"]) is not None
    assert validate_search_domains(["arxiv.org"], None) is None


def test_filter_hits_by_domains() -> None:
    hits = [
        {"url": "https://arxiv.org/abs/1", "title": "a", "snippet": ""},
        {"url": "https://reddit.com/x", "title": "b", "snippet": ""},
    ]
    out = filter_hits_by_domains(hits, allowed_domains=["arxiv.org"])
    assert len(out) == 1
    assert "arxiv" in out[0]["url"]


def test_permitted_redirect_www() -> None:
    assert permitted_redirect(
        "https://example.com/a",
        "https://www.example.com/b",
    )


def test_ojs_pdf_link_extraction() -> None:
    html = '<a href="/index.php/webmedia/article/download/38018/1234">PDF</a>'
    got = pick_ojs_pdf_url(html, "https://sol.sbc.org.br/page")
    assert got and "article/download/38018" in got


def test_citation_pdf_meta_extraction() -> None:
    html = (
        '<meta name="citation_pdf_url" '
        'content="https://sol.sbc.org.br/index.php/webmedia/article/download/38018/37796">'
    )
    got = extract_citation_pdf_url(html)
    assert got and "article/download/38018/37796" in got


def test_pdfjs_embedded_url() -> None:
    html = (
        'viewer.html?file=https%3A%2F%2Fsol.sbc.org.br%2Findex.php%2Fwebmedia%2F'
        'article%2Fdownload%2F38018%2F37796'
    )
    got = extract_pdfjs_embedded_url(html, "https://sol.sbc.org.br/viewer")
    assert got and "article/download/38018/37796" in got


def test_semantic_scholar_paper_id() -> None:
    url = (
        "https://www.semanticscholar.org/paper/"
        "Title-Slug/c7ceee9a2fd3cdff55efa53b86b97454d15a1647"
    )
    assert semantic_scholar_paper_id(url) == "c7ceee9a2fd3cdff55efa53b86b97454d15a1647"


@pytest.mark.asyncio
async def test_resolve_semantic_scholar_doi_to_ojs_pdf(monkeypatch) -> None:
    s2_url = (
        "https://www.semanticscholar.org/paper/"
        "Investigating-LLM/c7ceee9a2fd3cdff55efa53b86b97454d15a1647"
    )
    publisher_html = (
        '<meta name="citation_pdf_url" '
        'content="https://sol.sbc.org.br/index.php/webmedia/article/download/38018/37796">'
    )

    class FakeS2Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "openAccessPdf": None,
                "externalIds": {"DOI": "10.5753/webmedia.2025.16160"},
            }

    class FakeLandingResp:
        status_code = 200
        url = "https://sol.sbc.org.br/index.php/webmedia/article/view/38018"

        def raise_for_status(self):
            return None

        @property
        def headers(self):
            return {"content-type": "text/html; charset=utf-8"}

        @property
        def content(self):
            return publisher_html.encode("utf-8")

        @property
        def text(self):
            return publisher_html

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self._n = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aclose(self):
            return None

        async def get(self, url, **kwargs):
            if "api.semanticscholar.org" in url:
                return FakeS2Resp()
            if "doi.org" in url:
                return FakeLandingResp()
            raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        "app.agents.tools.source_resolve.httpx.AsyncClient",
        FakeClient,
    )
    got = await resolve_semantic_scholar_fetch_url(s2_url, timeout=5.0)
    assert got
    assert "article/download/38018/37796" in got


@pytest.mark.asyncio
async def test_resolve_landing_page_to_pdf_url_direct_pdf() -> None:
    pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"
    got = await resolve_landing_page_to_pdf_url(pdf_url, timeout=60.0)
    assert got
    assert "arxiv.org/pdf/1706.03762" in got


def test_work_url_from_openalex() -> None:
    work = {
        "doi": "https://doi.org/10.5555/test",
        "primary_location": {"landing_page_url": "https://publisher.example/paper"},
    }
    assert _work_url(work) == "https://publisher.example/paper"


@pytest.mark.asyncio
async def test_native_web_search_parses_html(monkeypatch) -> None:
    html = """
    <a class="result__a" href="https://example.edu/paper">Paper Title</a>
    <a class="result__snippet">Short abstract here.</a>
    """

    class FakeResp:
        status_code = 200
        text = html

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(
        "app.agents.tools.providers.native_search.httpx.AsyncClient",
        FakeClient,
    )
    data = await native_search("literature review", max_results=5)
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://example.edu/paper"


@pytest.mark.asyncio
async def test_native_fetch_sbc_ojs_pdf(monkeypatch) -> None:
    url = "https://sol.sbc.org.br/index.php/webmedia/article/view/38018"

    monkeypatch.setattr(
        "app.agents.tools.providers.native_fetch.pdf_bytes_to_text",
        lambda raw, backend="pypdf": "x" * 600,
    )
    result = await fetch_bytes(url, timeout=90.0)
    assert result.resolved_pdf_url and "article/download" in result.resolved_pdf_url
    if result.is_pdf:
        assert len(result.text) >= 500


@pytest.mark.asyncio
async def test_native_fetch_s2_resolves_doi_ojs_pdf(monkeypatch) -> None:
    s2_url = (
        "https://www.semanticscholar.org/paper/"
        "Investigating-LLM/c7ceee9a2fd3cdff55efa53b86b97454d15a1647"
    )

    async def fake_s2_record(paper_id: str, **kwargs):
        return {
            "openAccessPdf": None,
            "externalIds": {"DOI": "10.5753/webmedia.2025.16160"},
        }

    monkeypatch.setattr(
        "app.agents.tools.source_resolve.fetch_s2_paper_record",
        fake_s2_record,
    )
    monkeypatch.setattr(
        "app.agents.tools.providers.native_fetch.pdf_bytes_to_text",
        lambda raw, backend="pypdf": "y" * 600,
    )
    result = await fetch_bytes(s2_url, timeout=90.0)
    assert result.is_pdf
    assert len(result.text) >= 500
    assert result.resolved_pdf_url and "article/download" in result.resolved_pdf_url


@pytest.mark.asyncio
async def test_web_search_query_native_accepts_include_and_exclude_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_native_search(*_args, **kwargs):
        captured.update(kwargs)
        return {"results": [], "answer": ""}

    monkeypatch.setattr(native_search_provider, "search", fake_native_search)
    out = await web_search_query(
        "AI-native MOM",
        provider="native",
        include_domains=["arxiv.org"],
        exclude_domains=["reddit.com"],
    )
    assert out["results"] == []
    assert captured.get("include_domains") == ["arxiv.org"]
    assert captured.get("exclude_domains") == ["reddit.com"]


@pytest.mark.asyncio
async def test_openalex_search_returns_results_shape() -> None:
    data = await openalex_search("transformer efficiency", max_results=3)
    assert "results" in data
    assert isinstance(data["results"], list)
    if data["results"]:
        row = data["results"][0]
        assert "url" in row and "title" in row
