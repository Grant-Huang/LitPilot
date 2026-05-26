"""Library item dict builders and merge helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.library.canonical import canonical_key


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_authors(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if str(a).strip()]
    text = (raw or "").strip()
    if not text:
        return []
    if ";" in text and "," not in text[:80]:
        parts = text.split(";")
    else:
        parts = text.split(",")
    out: list[str] = []
    for p in parts:
        s = p.strip()
        if s and len(s) < 200:
            out.append(s)
    return out[:12]


def new_item(
    *,
    url: str,
    title: str = "",
    authors: str | list[str] | None = None,
    year: str = "",
    venue: str = "",
    doi: str = "",
    publisher: str = "",
    abstract: str = "",
    display_index: int | None = None,
) -> dict[str, Any]:
    cid = uuid4().hex[:16]
    key = canonical_key(url=url, doi=doi) or f"url:{cid}"
    now = utc_now()
    author_list = parse_authors(authors)
    return {
        "id": cid,
        "display_index": display_index or 0,
        "canonical_key": key,
        "title": (title or "").strip() or "Untitled",
        "authors": author_list,
        "venue": (venue or "").strip(),
        "year": (year or "").strip(),
        "citation_count": None,
        "url": (url or "").strip(),
        "doi": (doi or "").strip().rstrip("."),
        "publisher": (publisher or "").strip(),
        "abstract": (abstract or "").strip()[:2000],
        "summary_bullets": [],
        "full_text": None,
        "availability": {
            "has_abstract": bool((abstract or "").strip()),
            "has_full_text": False,
            "has_pdf": False,
            "fetch_status": "pending",
            "cite_status": "pending",
        },
        "citations": {},
        "provenance": [],
        "starred": False,
        "updated_at": now,
        "created_at": now,
    }


def merge_item(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    for field in (
        "title",
        "venue",
        "year",
        "url",
        "doi",
        "publisher",
        "abstract",
    ):
        new_val = (patch.get(field) or "").strip()
        old_val = (out.get(field) or "").strip()
        if field == "title":
            if new_val and (not old_val or len(new_val) > len(old_val)):
                out[field] = new_val
        elif new_val and not old_val:
            out[field] = new_val
        elif new_val and field == "abstract" and len(new_val) > len(old_val):
            out[field] = new_val

    if patch.get("authors"):
        merged = list(out.get("authors") or [])
        for a in patch["authors"]:
            if a not in merged:
                merged.append(a)
        out["authors"] = merged[:12]

    if patch.get("citation_count") is not None:
        out["citation_count"] = patch["citation_count"]

    if patch.get("citations"):
        cites = dict(out.get("citations") or {})
        cites.update(patch["citations"])
        out["citations"] = cites

    if patch.get("full_text"):
        out["full_text"] = patch["full_text"]

    if patch.get("availability"):
        av = dict(out.get("availability") or {})
        av.update(patch["availability"])
        out["availability"] = av
        out["availability"]["has_abstract"] = bool((out.get("abstract") or "").strip())

    if patch.get("summary_bullets"):
        out["summary_bullets"] = patch["summary_bullets"]

    if patch.get("starred") is not None:
        out["starred"] = bool(patch["starred"])

    prov = list(out.get("provenance") or [])
    for p in patch.get("provenance") or []:
        if not any(
            x.get("session_id") == p.get("session_id")
            and x.get("role") == p.get("role")
            for x in prov
        ):
            prov.append(p)
    out["provenance"] = prov[-20:]
    out["updated_at"] = utc_now()
    return out


def provenance_entry(
    session_id: str,
    role: str,
    *,
    session_title: str = "",
    review_ref_index: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "session_id": session_id,
        "role": role,
        "turn_at": utc_now(),
    }
    if session_title:
        row["session_title"] = session_title
    if review_ref_index is not None:
        row["review_ref_index"] = review_ref_index
    return row
