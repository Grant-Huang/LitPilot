from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.deploy_defaults import deploy_settings, defaults_path
from app.main import app
from app.storage import file_store
from app.storage.file_store import FileStore


def test_deploy_defaults_file_exists() -> None:
    assert defaults_path().is_file()
    settings = deploy_settings()
    assert settings.get("llm_model") == "MiniMax-M3"
    assert settings.get("orchestrator_model") == "MiniMax-M2.7-highspeed"
    assert "review_system_prompt_template" in settings
    assert "你是学术文献综述助手" in str(settings["review_system_prompt_template"])
    assert "tavily_api_key" not in settings
    assert "llm_api_key" not in settings


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


@pytest.fixture
def client(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(file_store, "_store", store)
    return TestClient(app)


def test_migration_seeds_prompt_from_deploy_defaults(
    client: TestClient,
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    client.get("/api/settings/system/capabilities")

    caps = store.list_system_capabilities()
    prompts = next(c for c in caps if c.get("capability_id") == "prompts")
    tpl = str(prompts.get("params", {}).get("review_system_prompt_template") or "")
    assert "你是学术文献综述助手" in tpl
