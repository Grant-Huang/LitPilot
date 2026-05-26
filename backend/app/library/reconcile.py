"""Reconcile library from session messages and artifacts."""
from __future__ import annotations

from typing import Any, Literal

from app.library.from_run import upsert_library_from_run
from app.library.migrate import migrate_legacy_refs
from app.library.store import LibraryStore
from app.skills.citation_extractor import (
    CitationRecord,
    extract_and_persist_batch,
    extract_citation_from_url,
)
from app.storage.file_store import get_store

ReconcileMode = Literal["session", "all", "failed_only"]


async def reconcile_library(
    *,
    session_id: str | None = None,
    mode: ReconcileMode = "session",
    jina_api_key: str | None = None,
    timeout: float = 60.0,
    citation_format: str = "apa",
) -> dict[str, Any]:
    lib = LibraryStore()
    if not lib.list_items():
        migrate_legacy_refs(lib)

    store = get_store()
    retried = 0
    added = 0
    merged = 0

    sessions: list[str] = []
    if mode == "all":
        sessions = [s["id"] for s in store.list_sessions()]
    elif session_id:
        sessions = [session_id]
    else:
        return {"error": "session_id required for mode=session"}

    for sid in sessions:
        meta = store.get_session(sid) or {}
        title = str(meta.get("title") or "")
        msgs = store.load_messages(sid, limit=100)
        failed: list[dict[str, str]] = []
        for msg in msgs:
            mmeta = msg.get("meta") or {}
            for f in mmeta.get("failed_literature") or []:
                failed.append(f)

        review = store.get_latest_review(sid)
        review_text = (review or {}).get("content") or ""

        if mode == "failed_only":
            hits = [{"url": f["url"], "title": f.get("title") or ""} for f in failed]
            cite_recs: list[CitationRecord] = []
            fetch_results = [(h, "", f.get("reason")) for h in hits]
        else:
            hits = _urls_from_trace(msgs)
            fetch_results = [(h, "", None) for h in hits]
            cite_recs = []

        result = upsert_library_from_run(
            sid,
            fetch_results=fetch_results,
            cite_records=cite_recs,
            failed_literature=failed,
            review_text=review_text,
            session_title=title,
            citation_format=citation_format,  # type: ignore[arg-type]
        )
        added += result.get("added", 0)
        merged += result.get("merged", 0)

        if mode == "failed_only" and failed:
            for fail in failed:
                url = fail.get("url") or ""
                if not url:
                    continue
                item = lib.find_by_url_or_doi(url=url)
                if not item:
                    continue
                av = item.get("availability") or {}
                if av.get("fetch_status") != "failed" and av.get("cite_status") != "failed":
                    continue
                rec = await extract_citation_from_url(
                    url,
                    jina_api_key=jina_api_key,
                    title_hint=fail.get("title") or "",
                    timeout=timeout,
                )
                from app.library.upsert_citation import upsert_from_citation

                upsert_from_citation(
                    rec,
                    lib=lib,
                    session_id=sid,
                    session_title=title,
                    citation_format=citation_format,  # type: ignore[arg-type]
                )
                if rec.success and not (item.get("full_text") or {}).get("path"):
                    try:
                        from app.agents.tools.jina_reader import jina_fetch

                        body = await jina_fetch(url, api_key=jina_api_key, timeout=timeout)
                        lib.save_full_text(item["id"], body)
                    except Exception:
                        pass
                retried += 1

    from app.library.from_run import _sync_exports

    _sync_exports(lib)
    return {
        "added": added,
        "merged": merged,
        "retried": retried,
        "total": len(lib.list_items()),
    }


def _urls_from_trace(msgs: list[dict[str, Any]]) -> list[dict[str, str]]:
    urls: list[dict[str, str]] = []
    seen: set[str] = set()
    for msg in msgs:
        trace = (msg.get("meta") or {}).get("execution_trace") or {}
        for tool in trace.get("tools") or []:
            if tool.get("name") != "web_fetch":
                continue
            args = tool.get("args") or {}
            url = str(args.get("url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                urls.append({"url": url, "title": str(args.get("title") or "")})
        for wf in trace.get("workflows") or []:
            url = str(wf.get("url") or "").strip()
            if url and url not in seen:
                seen.add(url)
                urls.append({"url": url, "title": str(wf.get("title") or "")})
    return urls
