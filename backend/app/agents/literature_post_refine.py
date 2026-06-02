"""Post-generation refine pass (M3)."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.literature_outline import LiteratureOutline

_BOILERPLATE = re.compile(
    r"(?im)^(?:\s*[-*]\s*)?(?:in conclusion|in summary|in essence|综上所述|总之)[，,：:\s].*$"
)
_DUP_HEADER = re.compile(r"^(#{1,3})\s+(.+)$", re.M)


def _outline_titles(outline: LiteratureOutline | None) -> list[str]:
    if not outline:
        return []
    return [s.title.strip() for s in outline.sections if s.title.strip()]


def post_refine_review(
    text: str,
    *,
    outline: LiteratureOutline | None = None,
    cite_count: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Rule-based post refine; returns (text, report)."""
    raw = text or ""
    lines = raw.splitlines()
    cleaned: list[str] = []
    removed_boilerplate = 0
    for ln in lines:
        if _BOILERPLATE.match(ln.strip()):
            removed_boilerplate += 1
            continue
        cleaned.append(ln)
    out = "\n".join(cleaned)

    titles = _outline_titles(outline)
    missing_sections: list[str] = []
    lower = out.lower()
    for title in titles:
        if title and title.lower() not in lower:
            missing_sections.append(title)

    unverified_markers = out.count("待核实")

    report = {
        "removed_boilerplate": removed_boilerplate,
        "missing_sections": missing_sections,
        "unverified_markers": unverified_markers,
        "cite_count_hint": cite_count,
    }
    return out, report
