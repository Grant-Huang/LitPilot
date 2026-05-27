from pathlib import Path

import pytest

from app.library.canonical import canonical_key
from app.library.dedupe import dedupe_library
from app.library.from_run import upsert_library_from_run
from app.library.migrate import migrate_legacy_refs
from app.library.store import LibraryStore
from app.library.tags import normalize_tags
from app.skills.citation_extractor import CitationRecord
from app.storage.file_store import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


@pytest.fixture
def lib(store: FileStore) -> LibraryStore:
    return LibraryStore(store)


def test_canonical_key_doi_and_arxiv() -> None:
    assert canonical_key(doi="10.1234/abc").startswith("doi:")
    assert canonical_key(url="https://arxiv.org/abs/2102.10985") == "arxiv:2102.10985"


def test_upsert_dedupes_by_url(lib: LibraryStore) -> None:
    a = lib.upsert({"title": "Paper A", "url": "https://arxiv.org/abs/2102.10985"}, url="https://arxiv.org/abs/2102.10985")
    b = lib.upsert({"title": "Paper A longer title", "abstract": "An abstract"}, url="https://arxiv.org/pdf/2102.10985")
    assert a["id"] == b["id"]
    assert b["abstract"] == "An abstract"
    assert len(lib.list_items()) == 1


def test_save_full_text(lib: LibraryStore) -> None:
    item = lib.upsert({"title": "T", "url": "https://example.com/paper"}, url="https://example.com/paper")
    lib.save_full_text(item["id"], "# Hello\n\nBody")
    updated = lib.get_item(item["id"])
    assert updated["availability"]["has_full_text"] is True
    assert "Hello" in lib.read_full_text(item["id"])


def test_upsert_library_from_run(lib: LibraryStore) -> None:
    hit = {"url": "https://arxiv.org/abs/2401.00001", "title": "Test Paper"}
    rec = CitationRecord(
        title="Test Paper",
        authors="Alice, Bob",
        year="2024",
        venue="arXiv",
        doi="",
        url=hit["url"],
        success=True,
    )
    stats = upsert_library_from_run(
        "sess1",
        fetch_results=[(hit, "# Content", None)],
        cite_records=[rec],
        failed_literature=[],
        review_text="See [1] https://arxiv.org/abs/2401.00001 for details.",
        session_title="Demo",
        lib=lib,
    )
    assert stats["total"] >= 1
    items = lib.list_items()
    assert any(i["url"] == hit["url"] for i in items)


def test_migrate_legacy_dedupes(store: FileStore, lib: LibraryStore) -> None:
    store.append_ref_index(
        {
            "index": 1,
            "title": "A",
            "authors": "X",
            "year": "2024",
            "url": "https://arxiv.org/abs/2102.10985",
            "doi": "",
            "apa": "[1] X (2024). A.",
        }
    )
    store.append_ref_index(
        {
            "index": 2,
            "title": "A duplicate",
            "authors": "X",
            "year": "2024",
            "url": "https://arxiv.org/pdf/2102.10985",
            "doi": "",
            "apa": "[2] X (2024). A dup.",
        }
    )
    stats = migrate_legacy_refs(lib)
    assert stats["added"] + stats["merged"] >= 1
    dedupe_library(lib)
    assert len(lib.list_items()) == 1


def test_star_item(lib: LibraryStore) -> None:
    item = lib.upsert({"title": "S", "url": "https://example.com/s"}, url="https://example.com/s")
    starred = lib.set_starred(item["id"], True)
    assert starred is not None
    assert starred["starred"] is True


def test_delete_item(lib: LibraryStore) -> None:
    item = lib.upsert({"title": "D", "url": "https://example.com/d"}, url="https://example.com/d")
    lib.save_full_text(item["id"], "body")
    assert lib.delete_item(item["id"]) is True
    assert lib.get_item(item["id"]) is None
    assert lib.read_full_text(item["id"]) == ""


def test_normalize_tags_dedupes_case_insensitive() -> None:
    assert normalize_tags(["精读", " 精读 ", "AI", "ai"]) == ["精读", "AI"]


def test_set_tags_and_list_tags(lib: LibraryStore) -> None:
    a = lib.upsert({"title": "A", "url": "https://example.com/a"}, url="https://example.com/a")
    b = lib.upsert({"title": "B", "url": "https://example.com/b"}, url="https://example.com/b")
    lib.set_tags(a["id"], ["精读", "工业软件"])
    lib.set_tags(b["id"], ["精读"])
    tags = {t["name"]: t["count"] for t in lib.list_tags()}
    assert tags["精读"] == 2
    assert tags["工业软件"] == 1
    updated = lib.get_item(a["id"])
    assert updated is not None
    assert "精读" in updated["tags"]


def test_load_first_user_message(store: FileStore) -> None:
    meta = store.create_session(title="Review A")
    sid = meta["id"]
    store.append_message(sid, "assistant", "hello")
    store.append_message(sid, "user", "What is AI-native industrial software?")
    assert "AI-native" in store.load_first_user_message(sid)
