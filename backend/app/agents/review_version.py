"""Semantic review version ids: v1, v2 for full; v3a, v3b for refine."""
from __future__ import annotations

import re
from typing import Any

_FULL_RE = re.compile(r"^v(\d+)$", re.I)
_REFINE_RE = re.compile(r"^v(\d+)([a-z]+)$", re.I)


def _version_rows(meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not meta:
        return []
    return [r for r in (meta.get("review_versions") or []) if isinstance(r, dict)]


def _max_full_number(rows: list[dict[str, Any]]) -> int:
    best = 0
    for row in rows:
        vid = str(row.get("id") or row.get("version") or "")
        m = _FULL_RE.match(vid)
        if m:
            best = max(best, int(m.group(1)))
        m2 = _REFINE_RE.match(vid)
        if m2:
            best = max(best, int(m2.group(1)))
    return best


def _max_refine_suffix(rows: list[dict[str, Any]], base: str) -> str:
    base_l = base.lower()
    best = ""
    for row in rows:
        vid = str(row.get("id") or row.get("version") or "")
        m = _REFINE_RE.match(vid)
        if not m or m.group(1) != base_l.lstrip("v"):
            continue
        suffix = m.group(2).lower()
        if len(suffix) > len(best) or (
            len(suffix) == len(best) and suffix > best
        ):
            best = suffix
    return best


def _next_alpha_suffix(current: str) -> str:
    if not current:
        return "a"
    chars = list(current)
    i = len(chars) - 1
    while i >= 0:
        if chars[i] != "z":
            chars[i] = chr(ord(chars[i]) + 1)
            return "".join(chars)
        chars[i] = "a"
        i -= 1
    return "a" + "".join(chars)


def current_review_version_id(meta: dict[str, Any] | None) -> str | None:
    rows = _version_rows(meta)
    if not rows:
        return None
    last = rows[-1]
    return str(last.get("id") or last.get("version") or "") or None


def next_full_review_version_id(meta: dict[str, Any] | None) -> str:
    n = _max_full_number(_version_rows(meta)) + 1
    return f"v{n}"


def next_refine_review_version_id(meta: dict[str, Any] | None) -> str:
    rows = _version_rows(meta)
    current = current_review_version_id(meta)
    if not current:
        return next_full_review_version_id(meta)

    m_full = _FULL_RE.match(current)
    if m_full:
        base_num = m_full.group(1)
        suffix = _max_refine_suffix(rows, f"v{base_num}")
        return f"v{base_num}{_next_alpha_suffix(suffix)}"

    m_ref = _REFINE_RE.match(current)
    if m_ref:
        base_num = m_ref.group(1)
        suffix = _max_refine_suffix(rows, f"v{base_num}")
        return f"v{base_num}{_next_alpha_suffix(suffix)}"

    return next_full_review_version_id(meta)


def resolve_review_version_id(
    *,
    meta: dict[str, Any] | None,
    intent: str,
    full_regen: bool = False,
) -> str:
    if intent == "review_refine" and not full_regen:
        return next_refine_review_version_id(meta)
    return next_full_review_version_id(meta)
