"""Session-scoped literature corpus — load, merge, persist."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agents.url_list import sanitize_fetch_urls
from app.library.canonical import canonical_key, normalize_url
from app.library.store import LibraryStore
from app.storage.file_store import FileStore, get_store

MAX_BLOCK_CHARS = 14_000


@dataclass
class SessionCorpus:
    """In-memory corpus for a literature session turn."""

    tavily_answer: str = ""
    sources_md: list[str] = field(default_factory=list)
    fetch_hits: list[dict[str, str]] = field(default_factory=list)
    fetch_results: list[tuple[dict[str, str], str, str | None]] = field(
        default_factory=list
    )
    failed_literature: list[dict[str, str]] = field(default_factory=list)
    known_url_keys: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "tavily_answer": self.tavily_answer,
            "sources_md": self.sources_md,
            "fetch_hits": self.fetch_hits,
            "fetch_results": [
                [hit, (ctx or "")[:MAX_BLOCK_CHARS], err]
                for hit, ctx, err in self.fetch_results
            ],
            "failed_literature": self.failed_literature,
            "known_url_keys": sorted(self.known_url_keys),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SessionCorpus | None:
        if not data:
            return None
        corpus = cls(
            tavily_answer=str(data.get("tavily_answer") or ""),
            sources_md=list(data.get("sources_md") or []),
            fetch_hits=[dict(h) for h in (data.get("fetch_hits") or [])],
            failed_literature=[
                dict(f) for f in (data.get("failed_literature") or [])
            ],
            known_url_keys=set(data.get("known_url_keys") or []),
        )
        for row in data.get("fetch_results") or []:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            hit = dict(row[0]) if isinstance(row[0], dict) else {"url": str(row[0])}
            ctx = str(row[1] or "")
            err = str(row[2]) if len(row) > 2 and row[2] else None
            corpus.fetch_results.append((hit, ctx, err))
        if not corpus.known_url_keys:
            corpus.known_url_keys = corpus._keys_from_hits()
        return corpus

    def _keys_from_hits(self) -> set[str]:
        keys: set[str] = set()
        for hit in self.fetch_hits:
            url = str(hit.get("url") or "")
            key = canonical_key(url=url) or normalize_url(url)
            if key:
                keys.add(key)
        return keys

    def register_url(self, url: str) -> None:
        key = canonical_key(url=url) or normalize_url(url)
        if key:
            self.known_url_keys.add(key)

    def has_url(self, url: str) -> bool:
        key = canonical_key(url=url) or normalize_url(url)
        return bool(key and key in self.known_url_keys)

    def merge(self, other: SessionCorpus) -> None:
        if other.tavily_answer and not self.tavily_answer:
            self.tavily_answer = other.tavily_answer
        elif other.tavily_answer:
            self.tavily_answer = f"{self.tavily_answer}\n\n{other.tavily_answer}".strip()

        existing_blocks = set(self.sources_md)
        for block in other.sources_md:
            if block not in existing_blocks:
                self.sources_md.append(block)
                existing_blocks.add(block)

        seen_hit_keys = self.known_url_keys.copy()
        for hit in other.fetch_hits:
            url = str(hit.get("url") or "")
            key = canonical_key(url=url) or normalize_url(url)
            if key and key in seen_hit_keys:
                continue
            self.fetch_hits.append(hit)
            if key:
                seen_hit_keys.add(key)
                self.known_url_keys.add(key)

        seen_result_keys = {
            canonical_key(url=str(h.get("url") or "")) or normalize_url(str(h.get("url") or ""))
            for h, _, _ in self.fetch_results
        }
        for hit, ctx, err in other.fetch_results:
            url = str(hit.get("url") or "")
            key = canonical_key(url=url) or normalize_url(url)
            if key and key in seen_result_keys:
                continue
            self.fetch_results.append((hit, ctx, err))
            if key:
                seen_result_keys.add(key)

        fail_urls = {f.get("url") for f in self.failed_literature}
        for fail in other.failed_literature:
            if fail.get("url") not in fail_urls:
                self.failed_literature.append(fail)

    def source_block_count(self) -> int:
        return len(self.sources_md)

    def append_tavily_answer(self, answer: str) -> None:
        answer = (answer or "").strip()
        if not answer:
            return
        block = f"## [Tavily] 检索摘要\n\n{answer}\n"
        if block not in self.sources_md:
            self.sources_md.insert(0, block)
        self.tavily_answer = answer


def load_session_corpus(store: FileStore, session_id: str) -> SessionCorpus | None:
    data = store.load_corpus(session_id)
    return SessionCorpus.from_dict(data)


def save_session_corpus(
    store: FileStore,
    session_id: str,
    corpus: SessionCorpus,
) -> None:
    store.save_corpus(session_id, corpus.to_dict())


def corpus_from_library_session(session_id: str) -> SessionCorpus | None:
    """Rebuild corpus blocks from library items tied to this session."""
    lib = LibraryStore()
    items = [
        item
        for item in lib.list_items()
        if _item_belongs_session(item, session_id)
    ]
    if not items:
        return None

    corpus = SessionCorpus()
    for item in items:
        url = str(item.get("url") or "")
        if not url:
            continue
        hit = {
            "url": url,
            "title": str(item.get("title") or ""),
            "snippet": str(item.get("abstract") or "")[:500],
            "source": "library",
        }
        full_text = lib.read_full_text(str(item.get("id") or ""))
        err = None
        if full_text:
            header = hit["title"] or url
            block = full_text[:MAX_BLOCK_CHARS]
            if not block.lstrip().startswith("##"):
                block = f"## [网页材料] {header}\n\n{block}"
            corpus.sources_md.append(block)
        else:
            avail = item.get("availability") or {}
            if avail.get("fetch_status") == "failed":
                err = str(item.get("meta_error") or "抓取失败")
                corpus.failed_literature.append(
                    {
                        "url": url,
                        "title": hit["title"],
                        "reason": err,
                        "kind": "抓取网页",
                    }
                )
        corpus.fetch_hits.append(hit)
        corpus.fetch_results.append((hit, full_text or "", err))
        corpus.register_url(url)

    apa_lines = []
    for item in items:
        apa = (item.get("citations") or {}).get("apa") or ""
        if apa:
            apa_lines.append(apa)
    if apa_lines:
        corpus.sources_md.append(
            "## [Citations] 已收录引用\n\n" + "\n\n".join(apa_lines[-40:])
        )
    return corpus if corpus.fetch_hits or corpus.sources_md else None


def resolve_session_corpus(store: FileStore, session_id: str) -> SessionCorpus | None:
    saved = load_session_corpus(store, session_id)
    if saved and (saved.fetch_hits or saved.sources_md):
        return saved
    return corpus_from_library_session(session_id)


def filter_new_urls(corpus: SessionCorpus | None, urls: list[str]) -> list[str]:
    clean = sanitize_fetch_urls(urls)
    if not corpus:
        return clean
    return [u for u in clean if not corpus.has_url(u)]


def hits_from_urls(urls: list[str]) -> list[dict[str, str]]:
    return [
        {"url": u, "title": "", "snippet": "", "source": "upload"}
        for u in sanitize_fetch_urls(urls)
    ]


def collect_failed_urls(
    corpus: SessionCorpus | None,
    last_failed: list[dict[str, str]] | None,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for src in (last_failed or []) + (corpus.failed_literature if corpus else []):
        url = str(src.get("url") or "").strip()
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _item_belongs_session(item: dict[str, Any], session_id: str) -> bool:
    for prov in item.get("provenance") or []:
        if prov.get("session_id") == session_id:
            return True
    return False


def list_session_library_items(session_id: str) -> list[dict[str, Any]]:
    lib = LibraryStore()
    return [
        item
        for item in lib.list_items()
        if _item_belongs_session(item, session_id)
    ]
