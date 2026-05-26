"""Merge duplicate library items by canonical_key."""
from __future__ import annotations

from typing import Any

from app.library.models import merge_item
from app.library.store import LibraryStore
from app.library.from_run import _sync_exports


def dedupe_library(lib: LibraryStore | None = None) -> dict[str, int]:
    lib = lib or LibraryStore()
    removed = 0
    merged = 0

    def _op(db: dict[str, Any]) -> None:
        nonlocal removed, merged
        items: dict[str, Any] = db.get("items") or {}
        keys: dict[str, str] = db.get("keys") or {}
        by_key: dict[str, list[str]] = {}
        for iid, item in list(items.items()):
            k = item.get("canonical_key") or ""
            if k:
                by_key.setdefault(k, []).append(iid)
        for k, ids in by_key.items():
            if len(ids) < 2:
                continue
            ids.sort(
                key=lambda x: (
                    int(items[x].get("display_index") or 99999),
                    items[x].get("created_at") or "",
                )
            )
            keep, drop_list = ids[0], ids[1:]
            for drop in drop_list:
                items[keep] = merge_item(items[keep], items[drop])
                items.pop(drop, None)
                removed += 1
                merged += 1
            keys[k] = keep

    lib._with_lock(_op)
    _sync_exports(lib)
    return {"removed": removed, "merged": merged, "total": len(lib.list_items())}
