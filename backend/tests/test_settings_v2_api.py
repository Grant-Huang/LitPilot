from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import backend as storage_backend
from app.storage.file_store import (
    DEFAULT_ORCHESTRATOR_MODEL,
    DEFAULT_REVIEW_MODEL,
    FileStore,
)


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


@pytest.fixture
def client(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.storage.storage_settings import clear_runtime_turso_credentials

    # Force API to use the temp FileStore (avoids touching real data dir).
    monkeypatch.setattr(storage_backend, "_store", store)
    monkeypatch.setenv("LITPILOT_STORAGE_BACKEND", "file")
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    clear_runtime_turso_credentials()
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
    assert "storage" in data
    assert data["storage"]["backend"] == "file"

    # v2 files are created on first access
    assert store.system_credentials_path.is_file()
    assert store.system_instances_path.is_file()
    assert store.system_capabilities_path.is_file()
    assert store.personal_preferences_path.is_file()


def test_migration_creates_review_and_orchestrator_instances(
    client: TestClient,
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "minimax_cn")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    client.get("/api/settings/system/overview")

    by_name = {i["name"]: i for i in store.list_system_instances()}
    assert set(by_name) == {"review-main", "orchestrator"}
    assert by_name["review-main"]["model_name"] == DEFAULT_REVIEW_MODEL
    assert by_name["orchestrator"]["model_name"] == DEFAULT_ORCHESTRATOR_MODEL


def test_ensure_default_instances_backfills_orchestrator(store: FileStore) -> None:
    store.ensure_settings_v2_migrated()
    instances = store.list_system_instances()
    review = next(i for i in instances if i.get("name") == "review-main")
    review["model_name"] = "MiniMax-M2.7"
    store.save_system_instances([review])

    store.ensure_settings_v2_migrated()

    by_name = {i["name"]: i for i in store.list_system_instances()}
    assert by_name["review-main"]["model_name"] == DEFAULT_REVIEW_MODEL
    assert by_name["orchestrator"]["model_name"] == DEFAULT_ORCHESTRATOR_MODEL


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
def test_web_fetch_capability_test_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(url: str, **kwargs):
        return {
            "text": "# Sample\n\n" + ("x" * 120),
            "final_url": url,
            "is_pdf": False,
        }

    monkeypatch.setattr(
        "app.agents.tools.web_providers.web_fetch_url_with_meta",
        fake_fetch,
    )
    res = client.post(
        "/api/settings/system/capabilities/web_fetch/test",
        json={"url": "https://example.com/paper", "provider": "native"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["data"]["ok"] is True
    assert body["data"]["provider"] == "native"


def test_system_storage_get_and_save(client: TestClient, store: FileStore) -> None:
    res = client.get("/api/settings/system/storage")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["backend"] == "file"
    assert "turso_ready" in data

    save = client.put(
        "/api/settings/system/storage",
        json={
            "database_url": "libsql://test-db.turso.io",
            "auth_token": "secret-token-value",
        },
    )
    assert save.status_code == 200, save.text
    saved = save.json()["data"]
    assert saved["database_url"] == "libsql://test-db.turso.io"
    assert saved["has_auth_token"] is True
    assert saved["masked_auth_token"].endswith("alue")
    assert store.system_storage_path.is_file()

    keep = client.put(
        "/api/settings/system/storage",
        json={"database_url": "libsql://test-db.turso.io"},
    )
    assert keep.status_code == 200
    assert keep.json()["data"]["has_auth_token"] is True

