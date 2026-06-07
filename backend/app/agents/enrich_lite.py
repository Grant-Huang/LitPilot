"""Lightweight field extraction during fetch enrich (v2)."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.corpus_paper import EnrichLite

_METHOD_RE = re.compile(
    r"(?:method|approach|framework|propose[sd]?)[:\s]+(.{20,200})",
    re.I,
)
_FINDINGS_RE = re.compile(
    r"(?:findings?|results?|conclude[sd]?)[:\s]+(.{20,200})",
    re.I,
)


def extract_enrich_lite_from_text(
    text: str,
    *,
    year: str = "",
) -> EnrichLite:
    body = (text or "").strip()
    if not body:
        return EnrichLite(year=year)
    method = ""
    findings = ""
    m = _METHOD_RE.search(body[:4000])
    if m:
        method = m.group(1).strip()[:200]
    f = _FINDINGS_RE.search(body[:6000])
    if f:
        findings = f.group(1).strip()[:200]
    if not method:
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        for ln in lines[1:6]:
            if len(ln) > 30:
                method = ln[:200]
                break
    if not findings and len(body) > 80:
        findings = body[:200].replace("\n", " ")
    return EnrichLite(
        method_one_liner=method,
        findings_one_liner=findings,
        year=year,
    )


def enrich_lite_to_dict(lite: EnrichLite) -> dict[str, str]:
    return lite.to_dict()
