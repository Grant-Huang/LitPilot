"""Canonical keys for deduplication."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse, urlunparse


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
    except Exception:
        return u.lower().rstrip("/")
    host = (p.netloc or "").lower()
    path = (p.path or "").rstrip("/")
    if host.endswith("arxiv.org"):
        m = re.search(r"/(abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?", path, re.I)
        if m:
            return f"arxiv:{m.group(2).lower()}"
    qs = parse_qs(p.query)
    if "doi" in qs and qs["doi"]:
        return f"doi:{qs['doi'][0].lower()}"
    scheme = p.scheme.lower() or "https"
    return urlunparse((scheme, host, path, "", "", "")).lower()


def extract_arxiv_id(url: str) -> str:
    m = re.search(
        r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(?:v\d+)?",
        url or "",
        re.I,
    )
    return m.group(1).lower() if m else ""


def canonical_key(*, url: str = "", doi: str = "") -> str:
    d = (doi or "").strip().lower().rstrip(".")
    if d:
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
        return f"doi:{d}"
    ax = extract_arxiv_id(url)
    if ax:
        return f"arxiv:{ax}"
    norm = normalize_url(url)
    if norm.startswith("arxiv:"):
        return norm
    if norm:
        return f"url:{norm}"
    return ""
