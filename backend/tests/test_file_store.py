import tempfile
from pathlib import Path

import pytest

from app.storage.file_store import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


def test_create_session_and_messages(store: FileStore) -> None:
    meta = store.create_session("Test")
    sid = meta["id"]
    store.append_message(sid, "user", "hello")
    store.append_message(sid, "assistant", "hi")
    msgs = store.load_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_append_ref(store: FileStore) -> None:
    store.append_ref_line("[1] Author (2024). Title.")
    text = store.read_ref_list()
    assert "[1] Author" in text


def test_save_matrix_artifact(store: FileStore) -> None:
    meta = store.create_session("Matrix")
    _, version_id = store.save_matrix_artifact(meta["id"], "# Matrix")
    latest = store.get_latest_matrix(meta["id"])

    assert version_id.startswith("matrix_")
    assert latest is not None
    assert latest["filename"] == "matrix-latest.md"
    assert "# Matrix" in latest["content"]


def test_session_pin_and_rename(store: FileStore) -> None:
    meta = store.create_session("原标题")
    sid = meta["id"]
    updated = store.update_session(sid, title="新标题", pinned=True)
    assert updated is not None
    assert updated["title"] == "新标题"
    assert updated["pinned"] is True
    listed = store.list_sessions()
    assert listed[0]["id"] == sid
    assert listed[0]["pinned"] is True


def test_agent_settings_merge(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "env-key")
    store.save_agent_settings({"fetch_parallel": 5})
    caps = store.list_system_capabilities()
    for cap in caps:
        if cap.get("capability_id") == "web_search":
            cap.setdefault("params", {})["search_provider"] = "tavily"
    store.save_system_capabilities(caps)
    merged = store.get_agent_settings_merged()
    assert merged["web_search_api_key"] == "env-key"
    assert merged["fetch_parallel"] == 5
