"""Upsert library after a literature workflow run."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.agents.url_list import title_from_search_hit
from app.library.models import provenance_entry
from app.library.store import LibraryStore
from app.library.upsert_citation import upsert_from_citation
from app.skills.citation_extractor import CitationFormat, CitationRecord

_log = logging.getLogger(__name__)


def upsert_library_from_run(
    session_id: str,
    *,
    fetch_results: list[tuple[dict[str, str], str, str | None]],
    cite_records: list[CitationRecord],
    failed_literature: list[dict[str, str]],
    review_text: str = "",
    citation_format: CitationFormat = "apa",
    session_title: str = "",
    lib: LibraryStore | None = None,
) -> dict[str, Any]:
    lib = lib or LibraryStore()
    added = 0
    merged = 0
    ids: list[str] = []

    for hit, ctx_md, err in fetch_results:
        url = hit.get("url") or ""
        if not url:
            continue
        prov = [
            provenance_entry(
                session_id,
                "search_hit",
                session_title=session_title,
            )
        ]
        patch: dict[str, Any] = {
            "title": title_from_search_hit(hit, url=url),
            "url": url,
            "provenance": prov,
        }
        if ctx_md and not err:
            patch["availability"] = {"fetch_status": "ok"}
            try:
                item = lib.upsert(patch, url=url)
                lib.save_full_text(item["id"], ctx_md)
                _maybe_pdf_from_url(lib, item["id"], url)
                merged += 1 if item.get("created_at") != item.get("updated_at") else 0
                added += 1
                ids.append(item["id"])
            except Exception:
                _log.warning("upsert/save_full_text failed for %s", url[:80], exc_info=True)
        else:
            patch["availability"] = {
                "fetch_status": "failed",
                "cite_status": "pending",
            }
            try:
                item = lib.upsert(patch, url=url)
                ids.append(item["id"])
                added += 1
            except Exception:
                _log.warning("upsert failed for failed-fetch item %s", url[:80], exc_info=True)

    for rec in cite_records:
        before = lib.find_by_url_or_doi(url=rec.url, doi=rec.doi)
        item = upsert_from_citation(
            rec,
            lib=lib,
            citation_format=citation_format,
            session_id=session_id,
            session_title=session_title,
        )
        if item:
            ids.append(item["id"])
            if before:
                merged += 1
            else:
                added += 1

    for fail in failed_literature:
        url = fail.get("url") or ""
        if not url:
            continue
        patch = {
            "title": title_from_search_hit(
                {"title": fail.get("title") or "", "snippet": ""},
                url=url,
            ),
            "url": url,
            "provenance": [
                provenance_entry(
                    session_id,
                    "failed",
                    session_title=session_title,
                )
            ],
            "availability": {
                "fetch_status": "failed"
                if fail.get("kind") == "抓取网页"
                else "ok",
                "cite_status": "failed"
                if fail.get("kind") == "引用抽取"
                else "pending",
            },
        }
        err = fail.get("reason") or ""
        if err:
            patch.setdefault("meta_error", err)
        item = lib.upsert(patch, url=url)
        ids.append(item["id"])

    review_links = _parse_review_ref_urls(review_text)
    for ref_idx, url in review_links:
        item = lib.upsert(
            {
                "url": url,
                "provenance": [
                    provenance_entry(
                        session_id,
                        "cited_in_review",
                        session_title=session_title,
                        review_ref_index=ref_idx,
                    )
                ],
            },
            url=url,
        )
        ids.append(item["id"])

    _sync_exports(lib)
    unique_ids = list(dict.fromkeys(ids))
    result = {
        "added": added,
        "merged": merged,
        "item_ids": unique_ids,
        "total": len(lib.list_items()),
    }
    return result


def _sync_exports(lib: LibraryStore) -> None:
    from app.storage.file_store import _write_json_atomic

    text = lib.export_ref_list_text()
    ref_path = lib.fs.root / "refs" / "ref-list.txt"
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = ref_path.with_suffix(".txt.tmp")
    tmp.write_text(text, encoding="utf-8")
    import os
    os.replace(str(tmp), str(ref_path))
    _write_json_atomic(lib.fs.root / "refs" / "index.json", lib.sync_legacy_index())


def _maybe_pdf_from_url(lib: LibraryStore, item_id: str, url: str) -> None:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        name = f"{item_id}.pdf"
        dest = lib.fs.root / "pdfs" / name
        if not dest.is_file():
            try:
                import urllib.request

                urllib.request.urlretrieve(url, dest)  # noqa: S310
                lib.link_pdf(item_id, name)
            except Exception:
                pass


def _parse_review_ref_urls(text: str) -> list[tuple[int, str]]:
    if not text:
        return []
    out: list[tuple[int, str]] = []
    for m in re.finditer(
        r"\[(\d+)\][^\n]*?(https?://[^\s\)\]>]+)",
        text,
    ):
        out.append((int(m.group(1)), m.group(2).rstrip(".,;")))
    return out
