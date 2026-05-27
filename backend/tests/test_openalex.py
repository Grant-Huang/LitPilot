"""Tests for OpenAlex DOI lookup."""
from __future__ import annotations

from app.library.openalex import lookup_doi_openalex, _title_similarity
from app.skills.citation_extractor import CitationRecord
from app.library.metadata_enrich import build_enrich_patch_for_record, resolve_doi_for_record


def test_title_similarity() -> None:
    assert _title_similarity(
        "Attention Is All You Need",
        "Attention is all you need",
    ) >= 0.8


def test_lookup_doi_openalex_parses(monkeypatch) -> None:
    sample = {
        "results": [
            {
                "title": "Sample Paper on Machine Learning",
                "doi": "https://doi.org/10.1234/abc.2024",
                "publication_year": 2024,
                "authorships": [
                    {"author": {"display_name": "Jane Smith"}},
                ],
            }
        ]
    }

    class FakeResp:
        def read(self):
            import json

            return json.dumps(sample).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.library.openalex.urllib.request.urlopen",
        lambda *a, **k: FakeResp(),
    )
    doi = lookup_doi_openalex(
        "Sample Paper on Machine Learning",
        "Jane Smith",
        "2024",
    )
    assert doi == "10.1234/abc.2024"


def test_resolve_doi_uses_openalex_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.library.metadata_enrich.lookup_doi_openalex",
        lambda title, authors, year, **kw: "10.5555/openalex",
    )
    monkeypatch.setattr(
        "app.library.metadata_enrich.enrich_patch_from_doi",
        lambda doi: {"doi": doi, "citation_count": 3},
    )
    rec = CitationRecord(
        title="Some Title Here Long Enough",
        authors="A Author",
        year="2020",
        venue="",
        doi="",
        url="https://example.com/p",
        success=True,
    )
    patch = build_enrich_patch_for_record(rec)
    assert rec.doi == "10.5555/openalex"
    assert patch.get("citation_count") == 3


def test_resolve_doi_skips_openalex_when_parsed() -> None:
    rec = CitationRecord(
        title="T",
        authors="",
        year="",
        venue="",
        doi="10.1234/existing",
        url="https://x.com",
        success=True,
    )
    assert resolve_doi_for_record(rec) == "10.1234/existing"
