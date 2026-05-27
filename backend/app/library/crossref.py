"""Crossref metadata — 被引、他引（参考文献条数）与书目字段。"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_PREVIEW_LIMIT = 20


def normalize_doi(raw: str) -> str:
    d = (raw or "").strip().rstrip(".")
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d, flags=re.I)
    m = _DOI_RE.search(d)
    return m.group(0) if m else d


def fetch_crossref_work(doi: str, *, timeout: float = 10.0) -> dict[str, Any] | None:
    """Fetch bibliographic metadata from Crossref. Returns patch dict for library item."""
    d = normalize_doi(doi)
    if not d:
        return None
    url = f"https://api.crossref.org/works/{urllib.parse.quote(d)}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LitPilot/1.0 (mailto:support@litpilot.local)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    msg = data.get("message") or {}
    if not msg:
        return None

    title_list = msg.get("title") or []
    title = str(title_list[0]).strip() if title_list else ""

    authors: list[str] = []
    for author in msg.get("author") or []:
        if not isinstance(author, dict):
            continue
        given = str(author.get("given") or "").strip()
        family = str(author.get("family") or "").strip()
        name = f"{given} {family}".strip() or family or given
        if name:
            authors.append(name[:200])

    year = _year_from_crossref(msg)
    venue_list = msg.get("container-title") or msg.get("short-container-title") or []
    venue = str(venue_list[0]).strip() if venue_list else ""

    volume = str(msg.get("volume") or "").strip()
    issue = str(msg.get("issue") or "").strip()
    pages = str(msg.get("page") or "").strip()
    month = _month_from_crossref(msg)

    publisher_list = msg.get("publisher") or ""
    publisher = str(publisher_list).strip() if publisher_list else ""

    abstract = _crossref_abstract(msg.get("abstract") or "")

    cited_by = int(msg.get("is-referenced-by-count") or 0)
    refs_raw = msg.get("reference") or []
    references_count = len(refs_raw) if isinstance(refs_raw, list) else 0
    references_preview = _preview_references(refs_raw)

    resolved_doi = normalize_doi(str(msg.get("DOI") or d))

    patch: dict[str, Any] = {
        "doi": resolved_doi,
        "citation_count": cited_by,
        "references_count": references_count,
    }
    if title:
        patch["title"] = title[:500]
    if authors:
        patch["authors"] = authors[:12]
    if year:
        patch["year"] = year
    if venue:
        patch["venue"] = venue[:300]
    if volume:
        patch["volume"] = volume[:40]
    if issue:
        patch["issue"] = issue[:40]
    if pages:
        patch["pages"] = pages[:80]
    if month:
        patch["month"] = month
    if publisher:
        patch["publisher"] = publisher[:200]
    if abstract:
        patch["abstract"] = abstract[:2000]
    if references_preview:
        patch["references_preview"] = references_preview
    return patch


def _year_from_crossref(msg: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued", "created"):
        block = msg.get(key) or {}
        parts = block.get("date-parts") or []
        if parts and isinstance(parts[0], list) and parts[0]:
            return str(parts[0][0])
    return ""


def _month_from_crossref(msg: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued"):
        block = msg.get(key) or {}
        parts = block.get("date-parts") or []
        if parts and isinstance(parts[0], list) and len(parts[0]) > 1:
            return str(parts[0][1]).zfill(2)
    return ""


def _crossref_abstract(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _preview_references(refs_raw: Any) -> list[dict[str, str]]:
    if not isinstance(refs_raw, list):
        return []
    out: list[dict[str, str]] = []
    for ref in refs_raw:
        if not isinstance(ref, dict):
            continue
        title = str(ref.get("article-title") or ref.get("volume-title") or "").strip()
        year = ""
        parts = (ref.get("year") or "")
        if parts:
            year = str(parts).strip()
        doi = normalize_doi(str(ref.get("DOI") or ""))
        row: dict[str, str] = {}
        if title:
            row["title"] = title[:300]
        if year:
            row["year"] = year
        if doi:
            row["doi"] = doi
        if row:
            out.append(row)
        if len(out) >= _PREVIEW_LIMIT:
            break
    return out
