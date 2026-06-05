"""Authoritative Crossref merge and citation line rebuild."""
from __future__ import annotations

from app.library.metadata_enrich import merge_enrich_into_patch, rebuild_citation_lines


def test_merge_enrich_overwrites_scraped_title() -> None:
    patch = {
        "title": "Wrong Site Navigation Header Text Here",
        "authors": ["Bad Author"],
        "year": "1999",
        "venue": "Wrong",
        "doi": "",
        "url": "https://example.com/p",
    }
    enrich = {
        "title": "Correct Scholarly Title From Crossref",
        "authors": ["Alice Author", "Bob Author"],
        "year": "2021",
        "venue": "Nature",
        "doi": "10.1234/abc",
        "citation_count": 42,
    }
    merge_enrich_into_patch(patch, enrich, authoritative=True)
    assert patch["title"] == enrich["title"]
    assert patch["authors"] == enrich["authors"]
    assert patch["year"] == "2021"
    assert patch["venue"] == "Nature"
    assert patch["citation_count"] == 42


def test_rebuild_citation_lines() -> None:
    patch = {
        "title": "Deep Learning",
        "authors": ["A. Author"],
        "year": "2020",
        "venue": "Journal",
        "doi": "10.1/x",
        "url": "https://example.com",
    }
    rebuild_citation_lines(patch, display_index=3, citation_format="apa")
    apa = patch["citations"]["apa"]
    assert apa.startswith("[3] A. Author (2020).")
    assert "Deep Learning" in apa
