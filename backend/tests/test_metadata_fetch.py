"""Tests for metadata-first web_fetch pipeline."""
from __future__ import annotations

import pytest

from app.agents.tools.metadata_fetch import (
    arxiv_abs_url,
    extract_arxiv_abstract,
    extract_doi_from_url,
    extract_pmc_id_from_url,
    extract_ssrn_abstract,
    format_metadata_text,
    is_doi_url,
    is_junk_fetch_content,
    is_paywalled_host,
    is_ssrn_doi,
    ssrn_page_url_from_doi,
    normalize_native_fetch_url,
    reconstruct_openalex_abstract,
    try_metadata_fetch,
)


def test_extract_doi_from_url() -> None:
    assert extract_doi_from_url("https://doi.org/10.1109/ABC.2024.123") == "10.1109/ABC.2024.123"
    assert extract_doi_from_url("https://dx.doi.org/10.1234/xyz") == "10.1234/xyz"
    assert is_doi_url("https://doi.org/10.1/x")


def test_is_paywalled_host() -> None:
    assert is_paywalled_host("https://ieeexplore.ieee.org/document/123")
    assert is_paywalled_host("https://pmc.ncbi.nlm.nih.gov/articles/PMC123/")
    assert not is_paywalled_host("https://arxiv.org/abs/2301.00001")


def test_arxiv_abs_url_normalization() -> None:
    assert arxiv_abs_url("https://arxiv.org/pdf/2509.11691.pdf") == "https://arxiv.org/abs/2509.11691"
    assert arxiv_abs_url("https://arxiv.org/abs/2301.04999") == "https://arxiv.org/abs/2301.04999"


def test_normalize_native_fetch_url_keeps_abs() -> None:
    assert (
        normalize_native_fetch_url("https://arxiv.org/abs/2301.04999")
        == "https://arxiv.org/abs/2301.04999"
    )
    assert (
        normalize_native_fetch_url("https://arxiv.org/pdf/2301.04999")
        == "https://arxiv.org/pdf/2301.04999.pdf"
    )


def test_reconstruct_openalex_abstract() -> None:
    work = {
        "title": "Sample",
        "abstract_inverted_index": {
            "Hello": [0],
            "world": [1],
        },
    }
    assert reconstruct_openalex_abstract(work) == "Hello world"


def test_extract_arxiv_abstract() -> None:
    html = '<blockquote class="abstract mathjax">Abstract: Test abstract here.</blockquote>'
    got = extract_arxiv_abstract(html)
    assert "Test abstract here" in got


def test_extract_pmc_id_from_url() -> None:
    assert extract_pmc_id_from_url(
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12350765/"
    ) == "PMC12350765"


def test_is_ssrn_doi() -> None:
    assert is_ssrn_doi("10.2139/ssrn.5276793")
    assert ssrn_page_url_from_doi("10.2139/ssrn.5276793").endswith("abstract_id=5276793")


def test_is_junk_fetch_content() -> None:
    assert is_junk_fetch_content(
        "Preparing to download ... HHS Vulnerability Disclosure"
    )
    assert is_junk_fetch_content("Just a moment... challenges.cloudflare.com")
    assert not is_junk_fetch_content("A" * 120)


def test_extract_ssrn_abstract() -> None:
    html = (
        '<meta name="citation_abstract" content="'
        + ("Machine learning survey. " * 8)
        + '">'
    )
    got = extract_ssrn_abstract(html)
    assert "Machine learning survey" in got


def test_format_metadata_text() -> None:
    text = format_metadata_text(
        title="Paper",
        abstract="A" * 100,
        source_url="https://doi.org/10.1/x",
        doi="10.1/x",
        metadata_source="OpenAlex",
    )
    assert "# Paper" in text
    assert "OpenAlex" in text
    assert "A" * 100 in text


@pytest.mark.asyncio
async def test_try_metadata_fetch_openalex(monkeypatch: pytest.MonkeyPatch) -> None:
    long_abstract = " ".join(f"word{i}" for i in range(20))

    async def fake_openalex(doi: str, **kwargs):
        words = long_abstract.split()
        inv: dict[str, list[int]] = {}
        for i, w in enumerate(words):
            inv[w] = [i]
        return {
            "title": "Metadata Paper",
            "abstract_inverted_index": inv,
        }

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_openalex_work_by_doi",
        fake_openalex,
    )
    result = await try_metadata_fetch("https://doi.org/10.1109/TEST.2024.1", timeout=5.0)
    assert result is not None
    text, final_url, pdf_url, is_pdf = result
    assert "Metadata Paper" in text
    assert "OpenAlex" in text
    assert not is_pdf
    assert pdf_url is None
    assert "doi.org" in final_url


@pytest.mark.asyncio
async def test_try_metadata_fetch_unpaywall_prefers_arxiv_abs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_openalex(doi: str, **kwargs):
        return None

    async def fake_unpaywall(doi: str, **kwargs):
        return "https://arxiv.org/pdf/1706.03762.pdf"

    async def fake_arxiv(abs_url: str, **kwargs):
        return format_metadata_text(
            title="Attention",
            abstract="x" * 120,
            source_url=abs_url,
            metadata_source="arXiv",
        )

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_openalex_work_by_doi",
        fake_openalex,
    )

    async def fake_crossref(doi: str, **kwargs):
        return "", ""

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_crossref_abstract_by_doi",
        fake_crossref,
    )
    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_unpaywall_oa_pdf",
        fake_unpaywall,
    )
    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_arxiv_abs_page",
        fake_arxiv,
    )
    result = await try_metadata_fetch("https://doi.org/10.5555/paywalled", timeout=5.0)
    assert result is not None
    text, final_url, pdf_url, is_pdf = result
    assert not is_pdf
    assert "/abs/" in final_url
    assert pdf_url and "arxiv.org/pdf" in pdf_url
    assert "arXiv" in text


@pytest.mark.asyncio
async def test_try_metadata_fetch_europe_pmc(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_pmc(pmc_id: str, **kwargs):
        return ("PMC Title", "y" * 120, "10.1234/pmc.test")

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_pmc_metadata_by_pmcid",
        fake_pmc,
    )
    result = await try_metadata_fetch(
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12350765/",
        timeout=5.0,
    )
    assert result is not None
    text, final_url, _pdf, is_pdf = result
    assert "PMC" in text
    assert "PMC12350765" in final_url
    assert not is_pdf


@pytest.mark.asyncio
async def test_try_metadata_fetch_ssrn_doi(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_openalex(doi: str, **kwargs):
        return None

    async def fake_crossref(doi: str, **kwargs):
        return "", ""

    async def fake_ssrn(page_url: str, **kwargs):
        return format_metadata_text(
            title="SSRN Paper",
            abstract="z" * 120,
            source_url=page_url,
            metadata_source="SSRN",
        )

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_openalex_work_by_doi",
        fake_openalex,
    )
    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_crossref_abstract_by_doi",
        fake_crossref,
    )
    async def fake_s2(doi: str, **kwargs):
        return "", ""

    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_s2_abstract_by_doi",
        fake_s2,
    )
    monkeypatch.setattr(
        "app.agents.tools.metadata_fetch.fetch_ssrn_page",
        fake_ssrn,
    )
    result = await try_metadata_fetch(
        "https://doi.org/10.2139/ssrn.5276793",
        timeout=5.0,
    )
    assert result is not None
    text, _final, _pdf, is_pdf = result
    assert "SSRN" in text
    assert not is_pdf
