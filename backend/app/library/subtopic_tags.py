"""Subtopic tag helpers for library items and corpus papers."""
from __future__ import annotations

from typing import Any

SUBTOPIC_TAG_PREFIX = "st:"


def normalize_subtopic_id(raw: str) -> str:
    text = (raw or "").strip().lower()
    text = text.replace(" ", "_")
    return text[:64]


def subtopic_tag(subtopic_id: str) -> str:
    sid = normalize_subtopic_id(subtopic_id)
    return f"{SUBTOPIC_TAG_PREFIX}{sid}" if sid else ""


def parse_subtopic_ids(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for tag in tags or []:
        text = str(tag).strip()
        if text.startswith(SUBTOPIC_TAG_PREFIX):
            sid = text[len(SUBTOPIC_TAG_PREFIX) :].strip()
            if sid and sid not in out:
                out.append(sid)
    return out


def merge_subtopic_tags(
    existing: list[str] | None,
    new_ids: list[str] | None,
) -> list[str]:
    merged = list(existing or [])
    seen = set(merged)
    for sid in new_ids or []:
        tag = subtopic_tag(sid)
        if tag and tag not in seen:
            merged.append(tag)
            seen.add(tag)
    return merged


def subtopic_tags_field(item: dict[str, Any]) -> list[str]:
    explicit = item.get("subtopic_tags")
    if isinstance(explicit, list) and explicit:
        return [str(t) for t in explicit if str(t).strip()]
    return parse_subtopic_ids(item.get("tags"))


def patch_subtopic_tags(
    item: dict[str, Any],
    subtopic_ids: list[str],
) -> dict[str, Any]:
    tags = merge_subtopic_tags(subtopic_tags_field(item), subtopic_ids)
    stags = [normalize_subtopic_id(s) for s in subtopic_ids if normalize_subtopic_id(s)]
    return {"tags": tags, "subtopic_tags": stags}
