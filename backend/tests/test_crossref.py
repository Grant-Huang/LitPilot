"""Tests for Crossref metadata parsing."""
from __future__ import annotations

from app.library.crossref import fetch_crossref_work, normalize_doi


def test_normalize_doi() -> None:
    assert normalize_doi("https://doi.org/10.1234/abc") == "10.1234/abc"


def test_fetch_crossref_work_parses(monkeypatch) -> None:
    sample = {
        "message": {
            "DOI": "10.1234/test.2024",
            "title": ["Sample Paper Title"],
            "author": [{"given": "A", "family": "Author"}],
            "container-title": ["Journal of Tests"],
            "published-print": {"date-parts": [[2024, 3]]},
            "volume": "12",
            "issue": "3",
            "page": "100-110",
            "is-referenced-by-count": 42,
            "reference": [{"article-title": "Ref One", "year": "2020"}],
            "abstract": "<p>An abstract.</p>",
        }
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
        "app.library.crossref.urllib.request.urlopen",
        lambda *a, **k: FakeResp(),
    )
    patch = fetch_crossref_work("10.1234/test.2024")
    assert patch is not None
    assert patch["title"] == "Sample Paper Title"
    assert patch["citation_count"] == 42
    assert patch["references_count"] == 1
    assert patch["volume"] == "12"
    assert patch["pages"] == "100-110"
    assert "abstract" in patch
