"""Tests for session corpus persistence."""
from __future__ import annotations

from app.agents.session_corpus import (
    SessionCorpus,
    load_session_corpus,
    save_session_corpus,
)
from app.storage.file_store import FileStore


def test_corpus_roundtrip(tmp_path) -> None:
    store = FileStore(tmp_path)
    meta = store.create_session("test")
    corpus = SessionCorpus()
    corpus.sources_md.append("## block")
    corpus.fetch_hits.append({"url": "https://example.com/a", "title": "A"})
    corpus.register_url("https://example.com/a")
    save_session_corpus(store, meta["id"], corpus)
    loaded = load_session_corpus(store, meta["id"])
    assert loaded is not None
    assert loaded.sources_md == ["## block"]
    assert len(loaded.fetch_hits) == 1


def test_corpus_merge() -> None:
    a = SessionCorpus()
    a.fetch_hits.append({"url": "https://a.com", "title": "A"})
    a.register_url("https://a.com")
    b = SessionCorpus()
    b.fetch_hits.append({"url": "https://b.com", "title": "B"})
    b.register_url("https://b.com")
    a.merge(b)
    assert len(a.fetch_hits) == 2
