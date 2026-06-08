"""Citation audit: range / unverified / uncited 校验。"""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.citation_audit import (
    audit_review_citations,
    extract_cited_indices,
)


@dataclass
class _Rec:
    title: str = ""
    url: str = ""
    success: bool = True
    error: str = ""


def test_extract_indices_handles_ranges_and_lists() -> None:
    text = "见 [1] 与 [2-4]，再参考 [3, 5] 和 [10]。"
    assert extract_cited_indices(text) == [1, 2, 3, 4, 3, 5, 10]


def test_audit_flags_out_of_range_and_unverified() -> None:
    recs = [
        _Rec(title="A", success=True),
        _Rec(title="B", success=False, error="DOI not resolved"),
        _Rec(title="C", success=True),
    ]
    review = "结果一致 [1]，但与 [2] 不同；另见 [4]（不存在）。"
    rep = audit_review_citations(review, recs)
    assert rep.total_records == 3
    assert rep.total_refs == 3
    assert rep.out_of_range == [4]
    assert any(u["index"] == "2" for u in rep.unverified)
    assert rep.uncited == [3]
    assert rep.has_issues


def test_audit_no_issues_when_all_cited_and_verified() -> None:
    recs = [_Rec(title="A", success=True), _Rec(title="B", success=True)]
    review = "讨论见 [1] 与 [2]。"
    rep = audit_review_citations(review, recs)
    assert not rep.has_issues
    assert rep.footer_lines() == []
    assert rep.uncited == []


def test_audit_empty_review_yields_uncited() -> None:
    recs = [_Rec(title="A", success=True)]
    rep = audit_review_citations("", recs)
    assert rep.uncited == [1]
    assert rep.total_refs == 0
