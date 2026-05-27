"""Free-form literature tags (route 1: per-item string tags)."""
from __future__ import annotations

import re
from typing import Any

MAX_TAGS_PER_ITEM = 20
MAX_TAG_LEN = 48


def normalize_tag(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip())
    if len(s) > MAX_TAG_LEN:
        s = s[:MAX_TAG_LEN].rstrip()
    return s


def normalize_tags(tags: Any) -> list[str]:
    if not tags:
        return []
    if not isinstance(tags, list):
        tags = [tags]
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        tag = normalize_tag(str(raw))
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
        if len(out) >= MAX_TAGS_PER_ITEM:
            break
    return out
