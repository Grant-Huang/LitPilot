"""Persist library.json and source files."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from filelock import FileLock

from app.library.canonical import canonical_key
from app.library.models import merge_item, new_item, utc_now
from app.library.tags import normalize_tags
from app.storage.file_store import FileStore, _read_json, _write_json_atomic, get_store


class LibraryStore:
    def __init__(self, file_store: FileStore | None = None) -> None:
        self.fs = file_store or get_store()
        self.root = self.fs.root
        self._ensure()

    def _ensure(self) -> None:
        (self.root / "sources").mkdir(parents=True, exist_ok=True)
        lib_path = self.root / "refs" / "library.json"
        if not lib_path.is_file():
            self._write_db({"version": 1, "next_display_index": 0, "items": {}, "keys": {}})

    @property
    def db_path(self) -> Path:
        return self.root / "refs" / "library.json"

    def _read_db(self) -> dict[str, Any]:
        return _read_json(self.db_path, {"version": 1, "next_display_index": 0, "items": {}, "keys": {}})

    def _write_db(self, data: dict[str, Any]) -> None:
        _write_json_atomic(self.db_path, data)

    def _with_lock(self, fn):
        lock = self.db_path.with_suffix(".library.lock")
        with FileLock(str(lock)):
            db = self._read_db()
            out = fn(db)
            self._write_db(db)
            return out

    def list_items(self) -> list[dict[str, Any]]:
        db = self._read_db()
        items = list((db.get("items") or {}).values())
        items.sort(key=lambda x: int(x.get("display_index") or 0))
        return items

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        db = self._read_db()
        return (db.get("items") or {}).get(item_id)

    def find_by_canonical(self, key: str) -> Optional[dict[str, Any]]:
        if not key:
            return None
        db = self._read_db()
        iid = (db.get("keys") or {}).get(key)
        if not iid:
            return None
        return (db.get("items") or {}).get(iid)

    def find_by_url_or_doi(self, *, url: str = "", doi: str = "") -> Optional[dict[str, Any]]:
        key = canonical_key(url=url, doi=doi)
        return self.find_by_canonical(key) if key else None

    def upsert(
        self,
        patch: dict[str, Any],
        *,
        url: str = "",
        doi: str = "",
    ) -> dict[str, Any]:
        key = canonical_key(url=url or patch.get("url", ""), doi=doi or patch.get("doi", ""))
        if not key and patch.get("canonical_key"):
            key = patch["canonical_key"]

        def _op(db: dict[str, Any]) -> dict[str, Any]:
            items: dict[str, Any] = db.setdefault("items", {})
            keys: dict[str, str] = db.setdefault("keys", {})
            existing = keys.get(key) if key else None
            if existing and existing in items:
                merged = merge_item(items[existing], patch)
                items[existing] = merged
                return merged
            nid = patch.get("id") or None
            if nid and nid in items:
                merged = merge_item(items[nid], patch)
                items[nid] = merged
                if key:
                    keys[key] = nid
                return merged
            next_idx = int(db.get("next_display_index") or 0) + 1
            db["next_display_index"] = next_idx
            item = new_item(
                url=url or patch.get("url", ""),
                title=patch.get("title", ""),
                authors=patch.get("authors") or [],
                year=patch.get("year", ""),
                venue=patch.get("venue", ""),
                doi=doi or patch.get("doi", ""),
                publisher=patch.get("publisher", ""),
                abstract=patch.get("abstract", ""),
                display_index=next_idx,
            )
            item["id"] = patch.get("id") or item["id"]
            merged = merge_item(item, patch)
            items[merged["id"]] = merged
            if key:
                keys[key] = merged["id"]
            return merged

        if not key and not patch.get("url"):
            raise ValueError("upsert requires url or canonical_key")
        return self._with_lock(_op)

    def save_full_text(self, item_id: str, text: str) -> Optional[dict[str, Any]]:
        body = (text or "").strip()
        if not body:
            return self.get_item(item_id)
        path = self.root / "sources" / f"{item_id}.md"
        path.write_text(body[:500_000], encoding="utf-8")
        patch = {
            "full_text": {
                "kind": "markdown",
                "path": f"sources/{item_id}.md",
                "char_count": len(body),
                "fetched_at": utc_now(),
            },
            "availability": {
                "has_full_text": True,
                "fetch_status": "ok",
            },
        }
        item = self.get_item(item_id)
        if not item:
            return None

        def _op(db: dict[str, Any]) -> dict[str, Any]:
            items = db["items"]
            merged = merge_item(items[item_id], patch)
            items[item_id] = merged
            return merged

        return self._with_lock(_op)

    def read_full_text(self, item_id: str) -> str:
        path = self.root / "sources" / f"{item_id}.md"
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def link_pdf(self, item_id: str, filename: str) -> Optional[dict[str, Any]]:
        patch = {
            "availability": {"has_pdf": True},
            "full_text": {
                "kind": "pdf",
                "path": f"pdfs/{filename}",
            },
        }

        def _op(db: dict[str, Any]) -> dict[str, Any]:
            items = db["items"]
            merged = merge_item(items[item_id], patch)
            items[item_id] = merged
            return merged

        return self._with_lock(_op)

    def set_starred(self, item_id: str, starred: bool) -> Optional[dict[str, Any]]:
        def _op(db: dict[str, Any]) -> Optional[dict[str, Any]]:
            items = db["items"]
            if item_id not in items:
                return None
            merged = merge_item(items[item_id], {"starred": starred})
            items[item_id] = merged
            return merged

        return self._with_lock(_op)

    def set_tags(self, item_id: str, tags: list[str]) -> Optional[dict[str, Any]]:
        normalized = normalize_tags(tags)

        def _op(db: dict[str, Any]) -> Optional[dict[str, Any]]:
            items = db["items"]
            if item_id not in items:
                return None
            merged = merge_item(items[item_id], {"tags": normalized})
            items[item_id] = merged
            return merged

        return self._with_lock(_op)

    def list_tags(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in self.list_items():
            for tag in item.get("tags") or []:
                name = str(tag).strip()
                if name:
                    counts[name] = counts.get(name, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(
                counts.items(),
                key=lambda x: (-x[1], x[0].casefold()),
            )
        ]

    def patch_item_metadata(
        self,
        item_id: str,
        patch: dict[str, Any],
        *,
        force_doi: bool = False,
    ) -> Optional[dict[str, Any]]:
        allowed = {
            "title",
            "authors",
            "year",
            "venue",
            "doi",
            "publisher",
            "abstract",
            "volume",
            "issue",
            "pages",
            "month",
        }
        clean = {k: v for k, v in patch.items() if k in allowed and v is not None}

        def _op(db: dict[str, Any]) -> Optional[dict[str, Any]]:
            items = db["items"]
            if item_id not in items:
                return None
            row = dict(items[item_id])
            if force_doi and clean.get("doi") is not None:
                from app.library.crossref import normalize_doi

                row["doi"] = normalize_doi(str(clean.pop("doi", "") or ""))
            merged = merge_item(row, clean)
            items[item_id] = merged
            return merged

        return self._with_lock(_op)

    def delete_item(self, item_id: str) -> bool:
        def _op(db: dict[str, Any]) -> bool:
            items: dict[str, Any] = db.get("items") or {}
            item = items.pop(item_id, None)
            if not item:
                return False
            keys = db.get("keys") or {}
            k = item.get("canonical_key")
            if k and keys.get(k) == item_id:
                keys.pop(k, None)
            src = self.root / "sources" / f"{item_id}.md"
            if src.is_file():
                src.unlink()
            return True

        return self._with_lock(_op)

    def export_ref_list_text(self) -> str:
        lines: list[str] = []
        for item in self.list_items():
            apa = (item.get("citations") or {}).get("apa") or ""
            if apa:
                lines.append(apa)
            ab = (item.get("abstract") or "").strip()
            if ab:
                lines.append(f"摘要: {ab[:400]}")
            lines.append("")
        return "\n".join(lines).strip() + ("\n" if lines else "")

    def sync_legacy_index(self) -> dict[str, Any]:
        """Expose items in legacy index.json shape for gradual migration."""
        refs = []
        for item in self.list_items():
            authors = ", ".join(item.get("authors") or [])
            refs.append(
                {
                    "index": item.get("display_index"),
                    "id": item.get("id"),
                    "format": "apa",
                    "citation": (item.get("citations") or {}).get("apa", ""),
                    "apa": (item.get("citations") or {}).get("apa", ""),
                    "title": item.get("title"),
                    "authors": authors,
                    "year": item.get("year"),
                    "venue": item.get("venue"),
                    "url": item.get("url"),
                    "doi": item.get("doi"),
                    "publisher": item.get("publisher"),
                    "abstract": item.get("abstract"),
                    "citation_count": item.get("citation_count"),
                    "availability": item.get("availability"),
                    "full_text": item.get("full_text"),
                    "provenance": item.get("provenance"),
                    "starred": item.get("starred"),
                    "canonical_key": item.get("canonical_key"),
                }
            )
        return {"refs": refs}
