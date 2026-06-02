"""Tests for v2 runtime settings bridge."""
from __future__ import annotations

import pytest

from app.agents.tools.tavily_search import ACADEMIC_SEARCH_DOMAINS, DEFAULT_EXCLUDE_DOMAINS
from app.storage.file_store import FileStore
from app.storage.runtime_settings import build_runtime_settings


@pytest.fixture
def store(tmp_path) -> FileStore:
    return FileStore(root=tmp_path)


def _seed_v2(
    store: FileStore,
    *,
    tavily_secret: str = "tvly-x",
    jina_secret: str = "jina-x",
    review_model: str = "gpt-test",
    web_search_params: dict | None = None,
    literature_source_mode: str = "merge",
    citation_format: str = "apa",
) -> None:
    store.ensure_settings_v2_migrated()
    creds = store.list_system_credentials()
    for c in creds:
        if c.get("type") == "tavily":
            c["secret"] = tavily_secret
            c["has_secret"] = bool(tavily_secret)
        if c.get("type") == "jina":
            c["secret"] = jina_secret
            c["has_secret"] = bool(jina_secret)
    store.save_system_credentials(creds)

    caps = store.list_system_capabilities()
    for cap in caps:
        if cap.get("capability_id") == "web_search" and web_search_params:
            cap["params"] = {**(cap.get("params") or {}), **web_search_params}
        if cap.get("capability_id") == "literature_source":
            cap["params"] = {"literature_source_mode": literature_source_mode}
    store.save_system_capabilities(caps)

    insts = store.list_system_instances()
    for inst in insts:
        if inst.get("name") == "review-main":
            inst["model_name"] = review_model
    store.save_system_instances(insts)

    store.save_personal_preferences({"citation_format": citation_format, "plan_confirm": True})


def test_build_runtime_settings_from_v2(store: FileStore) -> None:
    store.save_agent_settings(
        {
            "tavily_api_key": "legacy-should-not-win",
            "fetch_parallel": 6,
            "literature_source_mode": "user_only",
        }
    )
    _seed_v2(
        store,
        tavily_secret="tvly-runtime",
        review_model="MiniMax-M3",
        literature_source_mode="user_only",
        citation_format="ieee",
    )

    runtime = build_runtime_settings(
        credentials=store.list_system_credentials(),
        instances=store.list_system_instances(),
        capabilities=store.list_system_capabilities(),
        personal=store.get_personal_preferences(),
    )

    assert runtime["tavily_api_key"] == "tvly-runtime"
    assert runtime["fetch_parallel"] == 6
    assert runtime["llm_model"] == "MiniMax-M3"
    assert runtime["literature_source_mode"] == "user_only"
    assert runtime["citation_format"] == "ieee"
    assert runtime["plan_confirm"] is True
    assert runtime["tavily_include_domains"] == list(ACADEMIC_SEARCH_DOMAINS)


def test_get_agent_settings_merged_prefers_v2_over_env(store: FileStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "env-key")
    store.save_agent_settings({"fetch_parallel": 5})
    _seed_v2(store, tavily_secret="from-v2")

    merged = store.get_agent_settings_merged()
    assert merged["tavily_api_key"] == "from-v2"
    assert merged["fetch_parallel"] == 5


def test_custom_domain_lists(store: FileStore) -> None:
    _seed_v2(
        store,
        web_search_params={
            "include_domains": ["arxiv.org", "example.edu"],
            "exclude_domains": ["spam.com"],
            "search_depth": "basic",
            "enforce_domain_filter": False,
            "enable_junk_filter": False,
        },
    )
    merged = store.get_agent_settings_merged()
    assert merged["tavily_include_domains"] == ["arxiv.org", "example.edu"]
    assert merged["tavily_exclude_domains"] == ["spam.com"]
    assert merged["tavily_search_depth"] == "basic"
    assert merged["tavily_enforce_domain_filter"] is False
    assert merged["tavily_enable_junk_filter"] is False


def test_ensure_capability_param_defaults_backfills(store: FileStore) -> None:
    store.ensure_settings_v2_migrated()
    caps = store.list_system_capabilities()
    for cap in caps:
        if cap.get("capability_id") == "web_search":
            cap["params"] = {"tavily_max_results": 12}
    store.save_system_capabilities(caps)

    store.ensure_settings_v2_migrated()
    caps = store.list_system_capabilities()
    web = next(c for c in caps if c.get("capability_id") == "web_search")
    params = web["params"]
    assert params["tavily_max_results"] == 12
    assert params["include_domains"] == list(ACADEMIC_SEARCH_DOMAINS)
    assert params["exclude_domains"] == list(DEFAULT_EXCLUDE_DOMAINS)
    assert params["search_depth"] == "advanced"


@pytest.mark.asyncio
async def test_search_phase_uses_runtime_domains(tmp_path, monkeypatch) -> None:
    from unittest.mock import AsyncMock, patch

    from app.agents.literature_phases import stream_search_phase
    from app.core.think_stream import ThinkAccumulator

    store = FileStore(tmp_path)
    monkeypatch.setattr("app.agents.agent_settings.get_store", lambda: store)
    _seed_v2(
        store,
        tavily_secret="tvly-test",
        web_search_params={
            "include_domains": ["custom.example"],
            "exclude_domains": ["bad.example"],
            "search_depth": "basic",
            "enable_junk_filter": False,
            "enforce_domain_filter": True,
        },
    )

    tavily_mock = AsyncMock(return_value={"results": [], "answer": "ok"})
    events: list[tuple[str, dict]] = []
    think_acc = ThinkAccumulator()

    with patch("app.agents.literature_phases.cached_tavily_search", tavily_mock):
        async for ev in stream_search_phase(
            user_message="topic",
            query="topic academic",
            tavily_key="tvly-test",
            tavily_max_results=5,
            tavily_retry_count=0,
            fetch_retry_delay_ms=0,
            source_mode="merge",
            upload_count=0,
            skip_tavily=False,
            upload_urls=[],
            think_acc=think_acc,
            planner_ctx=None,
            execution_trace={},
            tavily_include_domains=("custom.example",),
            tavily_exclude_domains=("bad.example",),
            tavily_search_depth="basic",
            tavily_enforce_domain_filter=True,
            tavily_enable_junk_filter=False,
        ):
            events.append(ev)

    tavily_mock.assert_awaited_once()
    kwargs = tavily_mock.await_args.kwargs
    assert kwargs["search_depth"] == "basic"
    assert kwargs["include_domains"] == ("custom.example",)
    assert kwargs["exclude_domains"] == ("bad.example",)
