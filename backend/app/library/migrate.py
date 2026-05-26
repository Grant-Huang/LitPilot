"""Migrate legacy refs/index.json into library.json with dedupe."""
from __future__ import annotations

from typing import Any

from app.library.canonical import canonical_key
from app.library.models import merge_item, new_item, parse_authors
from app.library.store import LibraryStore
from app.storage.file_store import get_store


def migrate_legacy_refs(lib: LibraryStore | None = None) -> dict[str, int]:
    lib = lib or LibraryStore()
    fs = lib.fs
    legacy = fs.load_ref_index()
    refs = legacy.get("refs") or []
    added = 0
    merged = 0
    skipped = 0

    for row in refs:
        url = str(row.get("url") or "").strip()
        doi = str(row.get("doi") or "").strip()
        key = canonical_key(url=url, doi=doi)
        if not key:
            skipped += 1
            continue
        existing = lib.find_by_canonical(key)
        patch: dict[str, Any] = {
            "title": row.get("title") or "",
            "authors": parse_authors(str(row.get("authors") or "")),
            "year": str(row.get("year") or ""),
            "venue": str(row.get("venue") or ""),
            "url": url,
            "doi": doi,
            "publisher": str(row.get("publisher") or ""),
            "citations": {
                "apa": row.get("apa") or row.get("citation") or "",
            },
            "availability": {
                "fetch_status": "ok",
                "cite_status": "ok" if row.get("title") else "partial",
            },
        }
        ab_match = _abstract_from_ref_list(fs.read_ref_list(), int(row.get("index") or 0))
        if ab_match:
            patch["abstract"] = ab_match
            patch["availability"]["has_abstract"] = True

        if existing:
            lib._with_lock(
                lambda db, eid=existing["id"], p=patch: _merge_in_db(db, eid, p) or {}
            )
            merged += 1
        else:
            item = new_item(
                url=url,
                title=patch["title"],
                authors=patch["authors"],
                year=patch["year"],
                venue=patch.get("venue", ""),
                doi=doi,
                publisher=patch.get("publisher", ""),
                abstract=patch.get("abstract", ""),
                display_index=int(row.get("index") or 0) or None,
            )
            item = merge_item(item, patch)
            lib._with_lock(
                lambda db, it=item, k=key: _insert_in_db(db, it, k) or {}
            )
            added += 1

    ref_text = lib.export_ref_list_text()
    fs.root.joinpath("refs/ref-list.txt").write_text(ref_text, encoding="utf-8")
    idx = lib.sync_legacy_index()
    _write_json = __import__(
        "app.storage.file_store", fromlist=["_write_json_atomic"]
    )._write_json_atomic
    _write_json(fs.root / "refs" / "index.json", idx)
    return {"added": added, "merged": merged, "skipped": skipped}


def _abstract_from_ref_list(text: str, index: int) -> str:
    if not text or not index:
        return ""
    import re

    block = re.search(
        rf"^\[{index}\][\s\S]*?(?=^\[\d+\]|\Z)",
        text,
        re.MULTILINE,
    )
    if not block:
        return ""
    m = re.search(r"^摘要:\s*(.+)$", block.group(0), re.MULTILINE)
    return m.group(1).strip() if m else ""


def _merge_in_db(db: dict[str, Any], item_id: str, patch: dict[str, Any]) -> None:
    items = db["items"]
    items[item_id] = merge_item(items[item_id], patch)


def _insert_in_db(db: dict[str, Any], item: dict[str, Any], key: str) -> None:
    items = db.setdefault("items", {})
    keys = db.setdefault("keys", {})
    if keys.get(key) and keys[key] in items:
        items[keys[key]] = merge_item(items[keys[key]], item)
        return
    idx = int(db.get("next_display_index") or 0)
    if not item.get("display_index"):
        idx += 1
        item["display_index"] = idx
        db["next_display_index"] = max(int(db.get("next_display_index") or 0), idx)
    else:
        db["next_display_index"] = max(
            int(db.get("next_display_index") or 0),
            int(item["display_index"]),
        )
    items[item["id"]] = item
    keys[key] = item["id"]
