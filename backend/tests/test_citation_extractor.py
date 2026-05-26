from app.skills.citation_extractor import (
    CitationRecord,
    detect_publisher,
    normalize_citation_format,
    _extract_year,
)


def test_detect_publisher() -> None:
    assert detect_publisher("https://arxiv.org/abs/2301.00001") == "arxiv"
    assert detect_publisher("https://dl.acm.org/doi/10.1145/x") == "acm"


def test_normalize_citation_format() -> None:
    assert normalize_citation_format("acm") == "acm"
    assert normalize_citation_format("APA") == "apa"
    assert normalize_citation_format("unknown") == "apa"


def test_extract_year() -> None:
    assert _extract_year("Published in 2023 conference") == "2023"


def test_to_apa() -> None:
    rec = CitationRecord(
        title="Deep Learning",
        authors="A. Author",
        year="2020",
        venue="Nature",
        doi="10.1038/x",
        url="https://example.com",
        success=True,
    )
    apa = rec.to_apa(1)
    assert "[1]" in apa
    assert "Deep Learning" in apa
    assert "(2020)" in apa


def test_to_acm() -> None:
    rec = CitationRecord(
        title="Deep Learning",
        authors="A. Author",
        year="2020",
        venue="Nature",
        doi="10.1038/x",
        url="https://example.com",
        success=True,
    )
    acm = rec.to_acm(1)
    assert "[1]" in acm
    assert "Deep Learning" in acm
    assert "A. Author. 2020." in acm
    assert "DOI:https://doi.org/10.1038/x" in acm


def test_format_line() -> None:
    rec = CitationRecord(
        title="Survey",
        authors="B. Author",
        year="2021",
        venue="ACM",
        doi="",
        url="https://example.com/paper",
        success=True,
    )
    assert rec.format_line(2, "acm").startswith("[2] B. Author. 2021.")
    assert rec.format_line(2, "apa").startswith("[2] B. Author (2021).")
