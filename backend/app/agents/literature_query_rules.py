"""Shared literature search query heuristics (MOM disambiguation, etc.)."""
from __future__ import annotations

import re

# Strong manufacturing signals only — exclude weak "AI-native MOM" (ambiguous vs ML).
_MOM_STRONG_MANUFACTURING_RE = re.compile(
    r"(?i)"
    r"(?:"
    r"制造运营|"
    r"制造执行|"
    r"\bMES\b|"
    r"\bMOM\b.*(?:制造|manufactur|shop\s*floor|ISA-?95)|"
    r"manufacturing\s+operations\s+management"
    r")"
)

_MOM_TOKEN_RE = re.compile(r"\bMOM\b", re.I)


def is_mom_manufacturing_context(text: str) -> bool:
    return bool(_MOM_STRONG_MANUFACTURING_RE.search(text or ""))


def is_mom_ambiguous(text: str) -> bool:
    """MOM token present without clear manufacturing/MES context."""
    t = text or ""
    if not _MOM_TOKEN_RE.search(t):
        return False
    return not is_mom_manufacturing_context(t)
