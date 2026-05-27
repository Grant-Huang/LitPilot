"""Citation extraction — publisher routing + APA/ACM formatting."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from app.agents.tools.jina_reader import jina_fetch
from app.storage.file_store import get_store

CitationFormat = Literal["apa", "acm"]
SUPPORTED_CITATION_FORMATS: tuple[CitationFormat, ...] = ("apa", "acm")


def normalize_citation_format(fmt: str | None) -> CitationFormat:
    value = (fmt or "apa").strip().lower()
    if value in SUPPORTED_CITATION_FORMATS:
        return value  # type: ignore[return-value]
    return "apa"


@dataclass
class CitationRecord:
    title: str
    authors: str
    year: str
    venue: str
    doi: str
    url: str
    abstract: str = ""
    publisher: str = ""
    success: bool = False
    error: str = ""

    def to_apa(self, index: int) -> str:
        authors = self.authors or "Unknown"
        year = self.year or "n.d."
        title = self.title or "Untitled"
        venue = self.venue or ""
        doi_part = f" https://doi.org/{self.doi}" if self.doi else f" {self.url}"
        line = f"[{index}] {authors} ({year}). {title}."
        if venue:
            line += f" {venue}."
        line += doi_part.strip()
        return line

    def to_acm(self, index: int) -> str:
        authors = self.authors or "Unknown"
        year = self.year or "n.d."
        title = self.title or "Untitled"
        venue = self.venue or ""
        if self.doi:
            locator = f"DOI:https://doi.org/{self.doi}"
        else:
            locator = self.url
        line = f"[{index}] {authors}. {year}. {title}."
        if venue:
            line += f" {venue}."
        if locator:
            line += f" {locator}"
        return line.rstrip()

    def format_line(self, index: int, fmt: CitationFormat = "apa") -> str:
        if fmt == "acm":
            return self.to_acm(index)
        return self.to_apa(index)


def detect_publisher(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "arxiv.org" in host:
        return "arxiv"
    if "dblp.org" in host:
        return "dblp"
    if "acm.org" in host or "dl.acm.org" in host:
        return "acm"
    if "ieee" in host:
        return "ieee"
    if "semanticscholar.org" in host:
        return "semantic_scholar"
    if "sciencedirect" in host or "elsevier" in host:
        return "elsevier_blocked"
    if "researchgate" in host:
        return "researchgate_blocked"
    if "scholar.google" in host:
        return "google_scholar_blocked"
    return "generic"


def _next_ref_index() -> int:
    store = get_store()
    text = store.read_ref_list()
    nums = [int(m) for m in re.findall(r"^\[(\d+)\]", text, re.MULTILINE)]
    return max(nums, default=0) + 1


def _extract_year(text: str) -> str:
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return m.group(0) if m else ""


def _extract_title(text: str, fallback: str = "") -> str:
    for pat in (
        r"^#\s+(.+)$",
        r"Title:\s*(.+)",
        r"<title[^>]*>([^<]+)</title>",
    ):
        m = re.search(pat, text, re.I | re.M)
        if m:
            return m.group(1).strip()[:300]
    lines = [ln.strip() for ln in text.splitlines() if 20 < len(ln.strip()) < 200]
    if lines:
        return lines[0][:300]
    return fallback[:300]


def _extract_authors(text: str) -> str:
    m = re.search(
        r"(?:Authors?|By)[:\s]+([^\n]{5,200})",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip()[:200]
    return ""


def _extract_doi(text: str) -> str:
    m = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
    return m.group(0) if m else ""


def _extract_abstract(text: str) -> str:
    m = re.search(
        r"(?im)^#+\s*abstract\s*$[\s\S]*?(?=^#+\s|\Z)",
        text,
    )
    if m:
        block = re.sub(r"^#+\s*abstract\s*", "", m.group(0), flags=re.I).strip()
        block = re.sub(r"\s+", " ", block)
        if len(block) > 60:
            return block[:2000]
    m2 = re.search(
        r"(?is)(?:^|\n)\s*abstract\s*[:\-]\s*(.+?)(?:\n\s*(?:keywords|introduction|1\.|index terms)|\Z)",
        text,
    )
    if m2:
        block = re.sub(r"\s+", " ", m2.group(1).strip())
        if len(block) > 60:
            return block[:2000]
    return ""


async def extract_citation_from_url(
    url: str,
    *,
    jina_api_key: str | None = None,
    title_hint: str = "",
    timeout: float = 60.0,
) -> CitationRecord:
    publisher = detect_publisher(url)
    rec = CitationRecord(
        title=title_hint,
        authors="",
        year="",
        venue="",
        doi="",
        url=url,
        publisher=publisher,
    )

    if publisher in ("elsevier_blocked", "researchgate_blocked", "google_scholar_blocked"):
        rec.error = f"publisher blocked: {publisher}"
        return rec

    try:
        body = await jina_fetch(url, api_key=jina_api_key, timeout=timeout)
    except Exception as e:
        rec.error = str(e)
        return rec

    rec.title = _extract_title(body, title_hint)
    rec.authors = _extract_authors(body)
    rec.year = _extract_year(body)
    rec.doi = _extract_doi(body)

    if publisher == "arxiv":
        rec.venue = "arXiv preprint"
    elif publisher == "acm":
        rec.venue = rec.venue or "ACM"
    elif publisher == "ieee":
        rec.venue = rec.venue or "IEEE"

    abstract = _extract_abstract(body)
    if abstract:
        rec.abstract = abstract
    else:
        paras = [p.strip() for p in body.split("\n\n") if len(p.strip()) > 80]
        if paras:
            rec.abstract = paras[0][:500]

    rec.success = bool(rec.title and (rec.authors or rec.year))
    if not rec.success:
        rec.error = "insufficient metadata"
    return rec


async def persist_citation(
    rec: CitationRecord,
    *,
    citation_format: CitationFormat = "apa",
    session_id: str = "",
    session_title: str = "",
) -> Optional[dict[str, Any]]:
    """Upsert into global library (deduped) and sync legacy ref-list."""
    if not rec.success:
        return None

    from app.library.upsert_citation import upsert_from_citation
    from app.library.from_run import _sync_exports
    from app.library.store import LibraryStore

    item = upsert_from_citation(
        rec,
        citation_format=citation_format,
        session_id=session_id,
        session_title=session_title,
    )
    if not item:
        return None
    _sync_exports(LibraryStore())
    return {
        "index": item.get("display_index"),
        "id": item.get("id"),
        "format": citation_format,
        "citation": (item.get("citations") or {}).get(citation_format),
        "apa": (item.get("citations") or {}).get("apa"),
        "title": item.get("title"),
        "authors": ", ".join(item.get("authors") or []),
        "year": item.get("year"),
        "url": item.get("url"),
        "doi": item.get("doi"),
        "publisher": item.get("publisher"),
    }


async def extract_and_persist_batch(
    hits: list[dict[str, str]],
    *,
    jina_api_key: str | None = None,
    timeout: float = 60.0,
    max_items: int = 5,
    citation_format: CitationFormat = "apa",
    session_id: str = "",
    session_title: str = "",
) -> list[CitationRecord]:
    """Parallel Jina cite extract, then parallel OpenAlex+Crossref enrich, then persist."""
    import asyncio

    from app.agents.agent_settings import get_fetch_parallel
    from app.library.metadata_enrich import enrich_records_parallel
    from app.library.upsert_citation import upsert_from_citation
    from app.library.from_run import _sync_exports
    from app.library.store import LibraryStore

    queue = hits[:max_items]
    if not queue:
        return []

    parallel = await get_fetch_parallel()
    extract_sem = asyncio.Semaphore(max(1, min(parallel, 8)))

    async def _extract_one(hit: dict[str, str]) -> CitationRecord:
        async with extract_sem:
            return await extract_citation_from_url(
                hit["url"],
                jina_api_key=jina_api_key,
                title_hint=hit.get("title") or "",
                timeout=timeout,
            )

    results: list[CitationRecord] = list(
        await asyncio.gather(*[_extract_one(h) for h in queue])
    )

    success_recs = [r for r in results if r.success]
    enrich_list: list[dict] = []
    if success_recs:
        enrich_list = await enrich_records_parallel(
            success_recs,
            parallel=parallel,
        )

    enrich_iter = iter(enrich_list)
    lib = LibraryStore()
    for rec in results:
        if rec.success:
            ep = next(enrich_iter, {})
            upsert_from_citation(
                rec,
                lib=lib,
                citation_format=citation_format,
                session_id=session_id,
                session_title=session_title,
                enrich_patch=ep,
            )
        else:
            upsert_from_citation(
                rec,
                lib=lib,
                citation_format=citation_format,
                session_id=session_id,
                session_title=session_title,
            )

    if success_recs:
        _sync_exports(lib)

    return results
