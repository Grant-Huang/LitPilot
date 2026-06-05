"""Tests for structured citation metadata extraction."""
from __future__ import annotations

from app.skills.citation_meta import (
    extract_highwire_citation_meta,
    looks_like_title,
    merge_metadata_layers,
    sanitize_citation_fields,
)


SAMPLE_HTML = """
<html><head>
<meta name="citation_title" content="Attention Is All You Need" />
<meta name="citation_author" content="Ashish Vaswani" />
<meta name="citation_author" content="Noam Shazeer" />
<meta name="citation_publication_date" content="2017/06/12" />
<meta name="citation_conference_title" content="NeurIPS" />
<meta name="citation_doi" content="10.5555/3295222.3295349" />
</head><body></body></html>
"""


def test_extract_highwire_citation_meta() -> None:
    patch = extract_highwire_citation_meta(SAMPLE_HTML)
    assert patch["title"] == "Attention Is All You Need"
    assert "Ashish Vaswani" in patch["authors"]
    assert patch["year"] == "2017"
    assert patch["venue"] == "NeurIPS"
    assert patch["doi"] == "10.5555/3295222.3295349"


def test_merge_metadata_layers_later_wins() -> None:
    merged = merge_metadata_layers(
        {"title": "Wrong Nav Title", "authors": ["Foo"]},
        {"title": "Correct Paper Title", "authors": ["Bar Baz"], "year": "2020"},
    )
    assert merged["title"] == "Correct Paper Title"
    assert merged["authors"] == ["Bar Baz"]
    assert merged["year"] == "2020"


def test_sanitize_swaps_title_author_confusion() -> None:
    meta = sanitize_citation_fields(
        {
            "title": "Smith, J., Doe, A.",
            "authors": ["A Real Paper Title With Enough Words Here"],
        }
    )
    assert "Paper Title" in meta.get("title", "")


def test_looks_like_title_rejects_nav() -> None:
    assert not looks_like_title("Home | Publisher Site")
    assert looks_like_title("Machine Learning for Systems Design")
