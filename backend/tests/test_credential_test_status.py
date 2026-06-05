from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import backend as storage_backend
from app.storage.file_store import FileStore


@pytest.fixture
def client(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(storage_backend, "_store", store)
    return TestClient(app)


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


def test_credential_test_persists_ok_status(client: TestClient, store: FileStore) -> None:
    store.ensure_settings_v2_migrated()
    creds = store.list_system_credentials()
    tav = next(c for c in creds if c.get("type") == "tavily")
    tav["secret"] = "tvly-test-key-12345678901234567890123456789012"
    store.save_system_credentials(creds)

    with (
        patch("app.api.settings.search_credential_secret_hint", return_value=None),
        patch(
            "app.api.settings.tavily_provider_search",
            new_callable=AsyncMock,
            return_value={"results": [{}, {}, {}]},
        ),
    ):
        res = client.post(f"/api/settings/system/credentials/{tav['id']}/test", json={})

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["data"]["hits"] == 3
    assert body["data"]["credential"]["status"] == "ok"

    listed = client.get("/api/settings/system/credentials").json()
    tav_pub = next(x for x in listed["data"]["items"] if x["id"] == tav["id"])
    assert tav_pub["status"] == "ok"

    on_disk = next(c for c in store.list_system_credentials() if c["id"] == tav["id"])
    assert on_disk["status"] == "ok"
    assert on_disk["last_verified_at"]
