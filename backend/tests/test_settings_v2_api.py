from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import file_store
from app.storage.file_store import FileStore


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


@pytest.fixture
def client(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Force API to use the temp FileStore (avoids touching real data dir).
    monkeypatch.setattr(file_store, "_store", store)
    return TestClient(app)


def test_system_overview_triggers_migration(client: TestClient, store: FileStore) -> None:
    res = client.get("/api/settings/system/overview")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    data = body["data"]
    assert "credentials" in data
    assert "instances" in data
    assert "capabilities" in data

    # v2 files are created on first access
    assert store.system_credentials_path.is_file()
    assert store.system_instances_path.is_file()
    assert store.system_capabilities_path.is_file()
    assert store.personal_preferences_path.is_file()


def test_personal_preferences_roundtrip(client: TestClient) -> None:
    res = client.get("/api/settings/personal/preferences")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["data"]["citation_format"] in ("apa", "acm")
    assert isinstance(body["data"]["plan_confirm"], bool)

    res2 = client.put(
        "/api/settings/personal/preferences",
        json={"citation_format": "acm", "plan_confirm": True},
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["status"] == "success"
    assert body2["data"]["citation_format"] == "acm"
    assert body2["data"]["plan_confirm"] is True

    res3 = client.get("/api/settings/personal/preferences")
    assert res3.status_code == 200
    body3 = res3.json()
    assert body3["status"] == "success"
    assert body3["data"]["citation_format"] == "acm"
    assert body3["data"]["plan_confirm"] is True


def test_system_capability_single_card_save(client: TestClient) -> None:
    res = client.get("/api/settings/system/capabilities")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    items = body["data"]["items"]
    assert any(x.get("capability_id") == "web_fetch" for x in items)

    new_params = {
        "max_fetch_urls": 9,
        "fetch_parallel": 2,
        "fetch_timeout_sec": 33,
        "fetch_retry_count": 1,
        "fetch_retry_delay_ms": 700,
    }
    res2 = client.put(
        "/api/settings/system/capabilities/web_fetch",
        json={"params": new_params},
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["status"] == "success"
    assert body2["data"]["capability_id"] == "web_fetch"
    assert body2["data"]["params"]["max_fetch_urls"] == 9

    res3 = client.get("/api/settings/system/capabilities")
    assert res3.status_code == 200
    body3 = res3.json()
    assert body3["status"] == "success"
    items3 = body3["data"]["items"]
    fetch = next(x for x in items3 if x.get("capability_id") == "web_fetch")
    assert fetch["params"]["max_fetch_urls"] == 9
    assert fetch["params"]["fetch_parallel"] == 2

