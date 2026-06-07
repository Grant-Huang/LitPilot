"""Corpus paper record (v3): subtopic tags, fetch status, enrich lite fields."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FETCH_STATUS_OK = "ok"
FETCH_STATUS_FAILED = "fetch_failed"
FETCH_STATUS_SKIPPED = "queued_skipped"


@dataclass
class EnrichLite:
    method_one_liner: str = ""
    findings_one_liner: str = ""
    year: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "method_one_liner": self.method_one_liner,
            "findings_one_liner": self.findings_one_liner,
            "year": self.year,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EnrichLite:
        if not data:
            return cls()
        return cls(
            method_one_liner=str(data.get("method_one_liner") or ""),
            findings_one_liner=str(data.get("findings_one_liner") or ""),
            year=str(data.get("year") or ""),
        )


@dataclass
class CorpusPaperRecord:
    url: str
    title: str = ""
    library_id: str = ""
    subtopic_tags: list[str] = field(default_factory=list)
    fetch_status: str = FETCH_STATUS_OK
    has_pdf: bool = False
    enrich_lite: EnrichLite = field(default_factory=EnrichLite)
    cite_in_review: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "library_id": self.library_id,
            "subtopic_tags": list(self.subtopic_tags),
            "fetch_status": self.fetch_status,
            "has_pdf": self.has_pdf,
            "enrich_lite": self.enrich_lite.to_dict(),
            "cite_in_review": self.cite_in_review,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusPaperRecord:
        return cls(
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            library_id=str(data.get("library_id") or ""),
            subtopic_tags=[
                str(t) for t in (data.get("subtopic_tags") or []) if str(t).strip()
            ],
            fetch_status=str(data.get("fetch_status") or FETCH_STATUS_OK),
            has_pdf=bool(data.get("has_pdf")),
            enrich_lite=EnrichLite.from_dict(data.get("enrich_lite")),
            cite_in_review=bool(data.get("cite_in_review", True)),
        )

    @classmethod
    def from_legacy_paper_index(cls, data: dict[str, Any]) -> CorpusPaperRecord:
        url = str(data.get("url") or "")
        return cls(
            url=url,
            title=str(data.get("title") or ""),
            library_id=str(
                data.get("library_id") or data.get("paper_id") or data.get("id") or ""
            ),
            subtopic_tags=[
                str(t)
                for t in (data.get("subtopic_tags") or data.get("subtopics") or [])
                if str(t).strip()
            ],
            fetch_status=str(data.get("fetch_status") or FETCH_STATUS_OK),
            has_pdf=bool(data.get("has_pdf")),
            enrich_lite=EnrichLite(
                method_one_liner=str(
                    data.get("method_one_liner")
                    or (data.get("method") or "")[:200]
                ),
                findings_one_liner=str(
                    data.get("findings_one_liner")
                    or (data.get("findings") or "")[:200]
                ),
                year=str(data.get("year") or ""),
            ),
            cite_in_review=bool(data.get("cite_in_review", True)),
        )


def merge_corpus_papers(
    existing: list[dict[str, Any]],
    incoming: list[CorpusPaperRecord],
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in existing:
        url = str(row.get("url") or "")
        if url and url not in by_url:
            by_url[url] = dict(row)
            order.append(url)

    for rec in incoming:
        url = rec.url.strip()
        if not url:
            continue
        if url not in by_url:
            order.append(url)
            by_url[url] = rec.to_dict()
            continue
        prev = CorpusPaperRecord.from_dict(by_url[url])
        tags = list(prev.subtopic_tags)
        for t in rec.subtopic_tags:
            if t not in tags:
                tags.append(t)
        prev.subtopic_tags = tags
        if rec.title:
            prev.title = rec.title
        if rec.library_id:
            prev.library_id = rec.library_id
        if rec.fetch_status:
            prev.fetch_status = rec.fetch_status
        prev.has_pdf = prev.has_pdf or rec.has_pdf
        if rec.enrich_lite.method_one_liner:
            prev.enrich_lite.method_one_liner = rec.enrich_lite.method_one_liner
        if rec.enrich_lite.findings_one_liner:
            prev.enrich_lite.findings_one_liner = rec.enrich_lite.findings_one_liner
        if rec.enrich_lite.year:
            prev.enrich_lite.year = rec.enrich_lite.year
        prev.cite_in_review = rec.cite_in_review and prev.cite_in_review
        by_url[url] = prev.to_dict()

    return [by_url[u] for u in order if u in by_url]
