"""Tests for paper attribute extraction (M1)."""
from __future__ import annotations

from app.schemas.paper_record import PaperRecord, make_paper_id, normalize_attri
from app.skills.citation_extractor import CitationRecord
from app.skills.paper_attributes import (
    build_extraction_jobs,
    merge_paper_index,
    parse_attri_json,
    rule_based_attri,
)


def test_make_paper_id_stable() -> None:
    a = make_paper_id("https://arxiv.org/abs/1234.5678")
    b = make_paper_id("https://arxiv.org/abs/1234.5678")
    assert a == b
    assert len(a) == 12


def test_parse_attri_json() -> None:
    raw = '{"problem":"p","method":"m","datasets":"","findings":"f","limitations":"","keywords":["a"]}'
    attri = parse_attri_json(raw)
    assert attri is not None
    assert attri["problem"] == "p"
    assert attri["keywords"] == ["a"]


def test_rule_based_attri_from_title() -> None:
    attri = rule_based_attri(title="Transformer Survey Paper", snippet="We review transformers.")
    assert attri["problem"]
    assert isinstance(attri["keywords"], list)


def test_build_extraction_jobs_skips_existing_attri() -> None:
    url = "https://arxiv.org/abs/9999.0001"
    pid = make_paper_id(url)
    paper_index = [
        PaperRecord(
            paper_id=pid,
            url=url,
            title="Done",
            attri=rule_based_attri(title="Done", snippet="already"),
        ).to_dict()
    ]
    jobs = build_extraction_jobs(
        fetch_results=[({"url": url, "title": "Done"}, "body text", None)],
        cite_records=[],
        paper_index=paper_index,
    )
    assert jobs == []


def test_merge_paper_index_updates_and_preserves() -> None:
    url = "https://example.org/paper"
    pid = make_paper_id(url)
    existing = [{"paper_id": pid, "url": url, "title": "Old", "attri": {}}]
    fresh = [
        PaperRecord(
            paper_id=pid,
            url=url,
            title="New",
            attri=normalize_attri({"problem": "updated"}),
        )
    ]
    merged = merge_paper_index(existing, fresh)
    assert len(merged) == 1
    assert merged[0]["title"] == "New"
    assert merged[0]["attri"]["problem"] == "updated"


def test_build_extraction_jobs_uses_cite_title() -> None:
    url = "https://arxiv.org/abs/1111.2222"
    cite = CitationRecord(
        title="Cite Title",
        authors="A",
        year="2024",
        venue="v",
        doi="",
        url=url,
        abstract="abstract text",
        success=True,
    )
    jobs = build_extraction_jobs(
        fetch_results=[({"url": url, "title": "Hit Title"}, "ctx", None)],
        cite_records=[cite],
        paper_index=[],
    )
    assert len(jobs) == 1
    assert jobs[0].record.title == "Cite Title"
