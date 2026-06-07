"""Sanitize queries before academic API calls (no heavy imports)."""
from __future__ import annotations

import re

_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+",
)


def sanitize_academic_search_query(query: str) -> str:
    """Strip CJK — OpenAlex/arXiv/CrossRef match poorly on mixed zh/en queries."""
    q = _CJK_RE.sub(" ", query or "")
    q = re.sub(r"\s+", " ", q).strip()
    return q
