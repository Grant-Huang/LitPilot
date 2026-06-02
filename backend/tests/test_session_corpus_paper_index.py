"""Session corpus v2 paper_index roundtrip."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.session_corpus import SessionCorpus, save_session_corpus
from app.storage.file_store import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


def test_corpus_paper_index_roundtrip(store: FileStore) -> None:
    meta = store.create_session("Attr")
    corpus = SessionCorpus(
        sources_md=["## block"],
        paper_index=[
            {
                "paper_id": "abc123",
                "url": "https://arxiv.org/abs/1",
                "title": "Paper",
                "attri": {"problem": "p", "method": "", "datasets": "", "findings": "", "limitations": "", "keywords": []},
            }
        ],
    )
    save_session_corpus(store, meta["id"], corpus)
    loaded = store.load_corpus(meta["id"])
    assert loaded is not None
    assert loaded.get("version") == 2
    assert len(loaded.get("paper_index") or []) == 1

    restored = SessionCorpus.from_dict(loaded)
    assert restored is not None
    assert len(restored.paper_index) == 1
    assert restored.paper_index[0]["paper_id"] == "abc123"
