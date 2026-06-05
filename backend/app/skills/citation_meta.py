"""Structured bibliographic metadata from publisher APIs and HTML citation tags."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.agents.tools.source_resolve import semantic_scholar_paper_id


def _normalize_doi(raw: str) -> str:
    from app.library.crossref import normalize_doi

    return normalize_doi(raw)

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html)/([^/?#]+)",
    re.I,
)
_DOI_IN_URL_RE = re.compile(
    r"(?:doi\.org/|doi:)(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.I,
)
_NAV_TITLE_RE = re.compile(
    r"(?i)(home|login|sign in|404|not found|access denied|cookie|privacy)"
)
_AUTHOR_LIST_RE = re.compile(
    r"^(?:[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+){1,8}[A-Z][a-z]+(?:\s*,\s*)?$"
)


def extract_doi_from_url(url: str) -> str:
    m = _DOI_IN_URL_RE.search(url or "")
    return _normalize_doi(m.group(1)) if m else ""


def extract_arxiv_id(url: str) -> str:
    m = _ARXIV_ID_RE.search(url or "")
    if not m:
        return ""
    aid = m.group(1).strip().removesuffix(".pdf")
    return aid


def fetch_arxiv_metadata(url: str, *, timeout: float = 12.0) -> dict[str, Any]:
    """arXiv Atom API — title, authors, year, abstract."""
    aid = extract_arxiv_id(url)
    if not aid:
        return {}
    api_url = (
        "http://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({"id_list": aid})
    )
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "LitPilot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            root = ET.fromstring(resp.read())
    except Exception:
        return {}

    entry = root.find("atom:entry", _ATOM_NS)
    if entry is None:
        return {}

    title_el = entry.find("atom:title", _ATOM_NS)
    title = re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else ""

    authors: list[str] = []
    for author in entry.findall("atom:author", _ATOM_NS):
        name_el = author.find("atom:name", _ATOM_NS)
        if name_el is not None and (name_el.text or "").strip():
            authors.append(name_el.text.strip()[:200])

    published = entry.find("atom:published", _ATOM_NS)
    year = ""
    if published is not None and published.text:
        ym = re.match(r"(\d{4})", published.text.strip())
        if ym:
            year = ym.group(1)

    abstract_el = entry.find("atom:summary", _ATOM_NS)
    abstract = re.sub(r"\s+", " ", (abstract_el.text or "")).strip() if abstract_el is not None else ""

    patch: dict[str, Any] = {
        "publisher": "arxiv",
        "venue": "arXiv preprint",
    }
    if title:
        patch["title"] = title[:500]
    if authors:
        patch["authors"] = authors[:12]
    if year:
        patch["year"] = year
    if abstract:
        patch["abstract"] = abstract[:2000]
    return patch


async def fetch_semantic_scholar_metadata(
    url: str,
    *,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    paper_id = semantic_scholar_paper_id(url)
    if not paper_id:
        return {}
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    fields = (
        "title,authors,year,abstract,externalIds,"
        "publicationVenue,citationCount,venue"
    )
    api_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                api_url,
                params={"fields": fields},
                headers=headers,
            )
            if resp.status_code == 404:
                return {}
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    patch: dict[str, Any] = {"publisher": "semantic_scholar"}
    title = str(data.get("title") or "").strip()
    if title:
        patch["title"] = title[:500]

    authors: list[str] = []
    for a in data.get("authors") or []:
        if isinstance(a, dict):
            name = str(a.get("name") or "").strip()
            if name:
                authors.append(name[:200])
    if authors:
        patch["authors"] = authors[:12]

    year = data.get("year")
    if year:
        patch["year"] = str(year)

    venue_obj = data.get("publicationVenue")
    venue = ""
    if isinstance(venue_obj, dict):
        venue = str(venue_obj.get("name") or "").strip()
    if not venue:
        venue = str(data.get("venue") or "").strip()
    if venue:
        patch["venue"] = venue[:300]

    ext = data.get("externalIds")
    if isinstance(ext, dict):
        doi = _normalize_doi(str(ext.get("DOI") or ""))
        if doi:
            patch["doi"] = doi

    abstract = str(data.get("abstract") or "").strip()
    if abstract:
        patch["abstract"] = abstract[:2000]

    cc = data.get("citationCount")
    if cc is not None:
        try:
            patch["citation_count"] = int(cc)
        except (TypeError, ValueError):
            pass

    return patch


def extract_highwire_citation_meta(html: str) -> dict[str, Any]:
    """Parse Google Scholar / Highwire citation_* meta tags."""
    if not html or len(html) < 40:
        return {}

    soup = BeautifulSoup(html, "lxml")
    meta_map: dict[str, list[str]] = {}

    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").strip().lower()
        content = (tag.get("content") or "").strip()
        if not name or not content:
            continue
        meta_map.setdefault(name, []).append(unescape(content))

    def _first(*keys: str) -> str:
        for key in keys:
            vals = meta_map.get(key)
            if vals:
                return vals[0].strip()
        return ""

    title = _first(
        "citation_title",
        "dc.title",
        "dcterms.title",
        "og:title",
        "twitter:title",
    )
    authors: list[str] = []
    for key in ("citation_author", "dc.creator", "dcterms.creator"):
        for val in meta_map.get(key, []):
            name = val.strip()
            if name and name not in authors:
                authors.append(name[:200])

    date_raw = _first(
        "citation_publication_date",
        "citation_date",
        "dc.date",
        "dcterms.issued",
    )
    year = ""
    if date_raw:
        ym = re.search(r"\b(19|20)\d{2}\b", date_raw)
        if ym:
            year = ym.group(0)

    venue = _first(
        "citation_journal_title",
        "citation_conference_title",
        "citation_book_title",
        "prism.publicationname",
    )
    doi = _normalize_doi(
        _first("citation_doi", "dc.identifier", "dcterms.identifier")
        or ""
    )
    if not doi:
        for val in meta_map.get("dc.identifier", []) + meta_map.get("dcterms.identifier", []):
            found = _normalize_doi(val)
            if found:
                doi = found
                break

    abstract = _first("citation_abstract", "dc.description", "dcterms.abstract")
    if not abstract:
        abstract = _first("description")

    patch: dict[str, Any] = {}
    if title:
        patch["title"] = title[:500]
    if authors:
        patch["authors"] = authors[:12]
    if year:
        patch["year"] = year
    if venue:
        patch["venue"] = venue[:300]
    if doi:
        patch["doi"] = doi
    if abstract and len(abstract) >= 40:
        patch["abstract"] = abstract[:2000]
    return patch


def looks_like_title(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) < 8:
        return False
    if _NAV_TITLE_RE.search(t):
        return False
    if t.lower().startswith("http"):
        return False
    if re.fullmatch(r"[a-f0-9]{32,40}", t, re.I):
        return False
    # 整行像作者列表（多个人名逗号分隔、无动词）
    if t.count(",") >= 2 and len(t) < 120 and not re.search(r"[：:?]", t):
        parts = [p.strip() for p in t.split(",") if p.strip()]
        if len(parts) >= 2 and all(_AUTHOR_LIST_RE.match(p + ",") or len(p.split()) <= 4 for p in parts[:4]):
            return False
    return True


def looks_like_author_line(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 240:
        return False
    if re.search(r"(?i)\babstract\b|\bintroduction\b|\bkeywords\b", t):
        return False
    if t.count(".") > 2 and len(t) > 80:
        return False
    return True


def sanitize_citation_fields(meta: dict[str, Any]) -> dict[str, Any]:
    """Drop or swap fields that look mis-assigned."""
    out = dict(meta)
    title = str(out.get("title") or "").strip()
    authors = out.get("authors")
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]
    elif not isinstance(authors, list):
        authors = []

    venue = str(out.get("venue") or "").strip()

    if title and not looks_like_title(title):
        if authors and looks_like_title(", ".join(authors[:3])):
            out["title"] = ", ".join(authors[:3])[:500]
            out["authors"] = parse_author_tokens(title)
        else:
            out.pop("title", None)

    if venue and title and venue.strip().lower() == title.strip().lower():
        out.pop("venue", None)

    if authors:
        cleaned = [a for a in authors if looks_like_author_line(a)]
        if cleaned:
            out["authors"] = cleaned[:12]
        else:
            out.pop("authors", None)

    return out


def parse_author_tokens(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if ";" in text and text.count(";") >= text.count(","):
        parts = text.split(";")
    else:
        parts = text.split(",")
    return [p.strip()[:200] for p in parts if p.strip() and len(p.strip()) < 200][:12]


def merge_metadata_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    """Merge patches; later non-empty values win."""
    out: dict[str, Any] = {}
    for layer in layers:
        if not layer:
            continue
        for key, val in layer.items():
            if val is None:
                continue
            if key == "authors":
                if isinstance(val, list) and val:
                    out["authors"] = val[:12]
                elif isinstance(val, str) and val.strip():
                    out["authors"] = parse_author_tokens(val)
                continue
            if isinstance(val, str) and not val.strip():
                continue
            out[key] = val
    return sanitize_citation_fields(out)


def publisher_api_metadata(
    url: str,
    publisher: str,
    *,
    s2_api_key: str | None = None,
) -> dict[str, Any]:
    """Sync publisher lookups (arxiv); S2 handled async separately."""
    if publisher == "arxiv":
        return fetch_arxiv_metadata(url)
    if publisher == "semantic_scholar":
        return {}
    doi = extract_doi_from_url(url)
    if doi:
        return {"doi": doi}
    return {}
