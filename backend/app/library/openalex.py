"""OpenAlex — resolve DOI from title / authors when page parse has no DOI."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from app.library.crossref import normalize_doi

_MAILTO = "support@litpilot.local"
_USER_AGENT = f"LitPilot/1.0 (mailto:{_MAILTO})"


def _first_author_family(authors: str | list[str] | None) -> str:
    if isinstance(authors, list):
        raw = authors[0] if authors else ""
    else:
        raw = (authors or "").strip()
    if not raw:
        return ""
    if "," in raw:
        return raw.split(",")[0].strip().split()[-1][:80]
    parts = raw.split()
    return parts[-1][:80] if parts else ""


def _title_similarity(a: str, b: str) -> float:
    a_set = set(re.findall(r"[a-z0-9]+", (a or "").lower()))
    b_set = set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    if not a_set or not b_set:
        return 0.0
    inter = len(a_set & b_set)
    return inter / max(len(a_set), len(b_set))


def lookup_doi_openalex(
    title: str,
    authors: str | list[str] | None = None,
    year: str = "",
    *,
    timeout: float = 12.0,
) -> str | None:
    """Return normalized DOI if OpenAlex finds a confident match."""
    title_clean = re.sub(r"\s+", " ", (title or "").strip())[:300]
    if len(title_clean) < 8:
        return None

    filters: list[str] = [f"title.search:{title_clean}"]
    y = (year or "").strip()
    if y.isdigit() and len(y) == 4:
        filters.append(f"publication_year:{y}")
    family = _first_author_family(authors)
    if family and len(family) >= 2:
        filters.append(f"authorships.author.display_name.search:{family}")

    params = {
        "filter": ",".join(filters),
        "per-page": "8",
        "mailto": _MAILTO,
    }
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    results = data.get("results") or []
    if not results:
        return _lookup_doi_openalex_search_fallback(
            title_clean, authors, y, timeout=timeout
        )

    best_doi = ""
    best_score = 0.0
    for work in results:
        if not isinstance(work, dict):
            continue
        cand_title = _openalex_title(work)
        score = _title_similarity(title_clean, cand_title)
        if y and str(work.get("publication_year") or "") == y:
            score += 0.15
        if family and _author_family_in_work(family, work):
            score += 0.2
        doi_raw = str(work.get("doi") or "")
        doi = normalize_doi(doi_raw)
        if doi and score > best_score:
            best_score = score
            best_doi = doi

    if best_doi and best_score >= 0.45:
        return best_doi
    return None


def _lookup_doi_openalex_search_fallback(
    title: str,
    authors: str | list[str] | None,
    year: str,
    *,
    timeout: float,
) -> str | None:
    q = urllib.parse.urlencode(
        {
            "search": title[:200],
            "per-page": "8",
            "mailto": _MAILTO,
        }
    )
    url = f"https://api.openalex.org/works?{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except Exception:
        return None

    best_doi = ""
    best_score = 0.0
    family = _first_author_family(authors)
    for work in data.get("results") or []:
        if not isinstance(work, dict):
            continue
        cand_title = _openalex_title(work)
        score = _title_similarity(title, cand_title)
        if year and str(work.get("publication_year") or "") == year:
            score += 0.1
        if family and _author_family_in_work(family, work):
            score += 0.15
        doi = normalize_doi(str(work.get("doi") or ""))
        if doi and score > best_score:
            best_score = score
            best_doi = doi
    return best_doi if best_score >= 0.5 else None


def _openalex_title(work: dict[str, Any]) -> str:
    t = work.get("title") or work.get("display_name") or ""
    return str(t).strip()


def _author_family_in_work(family: str, work: dict[str, Any]) -> bool:
    fam = family.lower()
    for auth in work.get("authorships") or []:
        if not isinstance(auth, dict):
            continue
        author = auth.get("author") or {}
        if not isinstance(author, dict):
            continue
        disp = str(author.get("display_name") or "").lower()
        if fam in disp:
            return True
    return False
