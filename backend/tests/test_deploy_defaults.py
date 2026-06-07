from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.deploy_defaults import (
    deploy_credentials,
    deploy_instances,
    deploy_settings,
    defaults_path,
)
from app.main import app
from app.storage import backend as storage_backend
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


def test_deploy_catalog_has_stable_ids_and_bindings() -> None:
    creds = deploy_credentials()
    insts = deploy_instances()
    assert len(creds) >= 3
    assert len(insts) == 2
    cred_ids = {str(c["id"]) for c in creds}
    assert len(cred_ids) == len(creds)
    inst_ids = {str(i["id"]) for i in insts}
    assert len(inst_ids) == len(insts)
    cred_by_key = {str(c["key"]): str(c["id"]) for c in creds}
    for inst in insts:
        cred_key = str(inst.get("credential_key") or "llm_primary")
        assert inst.get("credential_key")
        assert cred_by_key.get(cred_key)
        assert str(inst.get("model_name") or "").strip()


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(root=tmp_path)


@pytest.fixture
def client(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(storage_backend, "_store", store)
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


def test_migration_uses_stable_instance_ids_and_binds_credentials(
    client: TestClient,
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    client.get("/api/settings/system/instances")

    instances = store.list_system_instances()
    creds = store.list_system_credentials()
    templates = {str(t["key"]): str(t["id"]) for t in deploy_instances()}
    cred_templates = {str(t["key"]): str(t["id"]) for t in deploy_credentials()}
    by_name = {str(i.get("name") or ""): i for i in instances}

    review = by_name["review-main"]
    orch = by_name["orchestrator"]
    assert str(review["id"]) == templates["review_main"]
    assert str(orch["id"]) == templates["orchestrator"]
    llm_cred_id = cred_templates["llm_primary"]
    assert str(review.get("credential_id") or "") == llm_cred_id
    assert str(orch.get("credential_id") or "") == llm_cred_id
    assert any(str(c.get("id") or "") == llm_cred_id for c in creds)

    resp = client.put(
        f"/api/settings/system/instances/{templates['review_main']}",
        json={"credential_id": llm_cred_id, "model_name": "MiniMax-M3"},
    )
    assert resp.status_code == 200, resp.text


def test_deploy_catalog_remaps_legacy_random_instance_ids(
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    now = "2020-01-01T00:00:00+00:00"
    legacy_cred_id = "deadbeef" * 4
    legacy_inst_id = "cafebabe" * 4
    store._save_config_list(
        store.system_credentials_path,
        [
            {
                "id": legacy_cred_id,
                "type": "llm:minimax_cn",
                "name": "LLM · minimax_cn · primary",
                "has_secret": True,
                "secret": "sk-test-key",
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            }
        ],
    )
    store._save_config_list(
        store.system_instances_path,
        [
            {
                "id": legacy_inst_id,
                "name": "review-main",
                "provider": "minimax_cn",
                "credential_id": legacy_cred_id,
                "model_name": "MiniMax-M3",
                "default_params": {},
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            }
        ],
    )
    store._save_config_list(
        store.system_capabilities_path,
        [
            {
                "capability_id": "review_main",
                "label": "文献综述生成",
                "enabled": True,
                "primary_ref": {"kind": "instance", "id": legacy_inst_id},
                "override_params": {},
                "params": {},
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    _write_prefs = store.personal_preferences_path
    _write_prefs.parent.mkdir(parents=True, exist_ok=True)
    _write_prefs.write_text(
        '{"preferences": {"citation_format": "apa"}, "created_at": "'
        + now
        + '", "updated_at": "'
        + now
        + '"}',
        encoding="utf-8",
    )

    store.ensure_settings_v2_migrated()

    instances = store.list_system_instances()
    creds = store.list_system_credentials()
    caps = store.list_system_capabilities()
    stable_inst = next(t for t in deploy_instances() if t["key"] == "review_main")
    stable_cred = next(t for t in deploy_credentials() if t["key"] == "llm_primary")
    review = next(i for i in instances if i.get("name") == "review-main")
    assert str(review["id"]) == str(stable_inst["id"])
    llm_cred = next(c for c in creds if str(c.get("type") or "").startswith("llm:"))
    assert str(llm_cred["id"]) == str(stable_cred["id"])
    review_cap = next(c for c in caps if c.get("capability_id") == "review_main")
    assert review_cap["primary_ref"]["id"] == str(stable_inst["id"])


def test_ensure_default_capabilities_backfills_web_search_and_fetch(
    store: FileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    now = "2020-01-01T00:00:00+00:00"
    legacy_cred_id = "deadbeef" * 4
    legacy_inst_id = "cafebabe" * 4
    store._save_config_list(
        store.system_credentials_path,
        [
            {
                "id": legacy_cred_id,
                "type": "llm:minimax_cn",
                "name": "LLM · minimax_cn · primary",
                "has_secret": True,
                "secret": "sk-test-key",
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            },
            {
                "id": "tavily-1",
                "type": "tavily",
                "name": "Tavily · default",
                "has_secret": False,
                "secret": "",
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            },
            {
                "id": "jina-1",
                "type": "jina",
                "name": "Jina · default",
                "has_secret": False,
                "secret": "",
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            },
        ],
    )
    store._save_config_list(
        store.system_instances_path,
        [
            {
                "id": legacy_inst_id,
                "name": "review-main",
                "provider": "minimax_cn",
                "credential_id": legacy_cred_id,
                "model_name": "MiniMax-M3",
                "default_params": {},
                "created_at": now,
                "updated_at": now,
                "status": "unknown",
                "last_verified_at": None,
            }
        ],
    )
    store._save_config_list(
        store.system_capabilities_path,
        [
            {
                "capability_id": "review_main",
                "label": "文献综述生成",
                "enabled": True,
                "primary_ref": {"kind": "instance", "id": legacy_inst_id},
                "override_params": {},
                "params": {},
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    prefs_path = store.personal_preferences_path
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(
        '{"preferences": {"citation_format": "apa"}, "created_at": "'
        + now
        + '", "updated_at": "'
        + now
        + '"}',
        encoding="utf-8",
    )

    store.ensure_settings_v2_migrated()

    cap_ids = {str(c.get("capability_id") or "") for c in store.list_system_capabilities()}
    assert "web_search" in cap_ids
    assert "web_fetch" in cap_ids
    assert "orchestrator" in cap_ids
    assert "prompts" in cap_ids
    cred_templates = {str(t["key"]): str(t["id"]) for t in deploy_credentials()}
    web_search = next(
        c for c in store.list_system_capabilities() if c["capability_id"] == "web_search"
    )
    web_fetch = next(
        c for c in store.list_system_capabilities() if c["capability_id"] == "web_fetch"
    )
    assert web_search["primary_ref"]["id"] == cred_templates["semantic_scholar"]
    assert web_fetch["primary_ref"]["id"] == cred_templates["jina"]
