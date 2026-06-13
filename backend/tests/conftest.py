"""Shared fixtures for literature pipeline live E2E tests.

Provides FileStore isolation, session seeding, fast LLM model injection,
and LLM call tracing.
All external I/O (LLM, search APIs, web fetching) uses REAL services.
Tests must be run with the ``live`` marker.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.storage.file_store import FileStore

from tests.helpers.e2e_mocks import SEED_REVIEW_MARKDOWN, seed_corpus_hits
from tests.helpers.llm_trace import LLMTraceCollector

# Non-review LLM roles use flash for speed; review keeps the full model.
_FAST_MODEL = "deepseek-v4-flash"


def _inject_fast_llm_config(store: FileStore) -> None:
    """Save LLM config so non-review roles use flash model."""
    from app.services.llm_service import reset_llm_cache
    from app.agents.agent_settings import _clear_all_caches

    settings: dict[str, Any] = {}
    for prefix in ("planner_llm", "router_llm", "pipeline_llm", "search_llm", "assessor_llm"):
        settings[f"{prefix}_model"] = _FAST_MODEL
    store.save_agent_settings(settings)

    _clear_all_caches()
    reset_llm_cache()


# ---------------------------------------------------------------------------
# LLM Trace fixture — wraps all LLM instances to capture prompts & responses
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_trace() -> LLMTraceCollector:
    """Collect all LLM calls during a test and print a trace report on teardown."""
    collector = LLMTraceCollector()

    # Patch build_llm to wrap every new LLM instance with tracing
    from app.llm import factory as _factory

    original_build = _factory.build_llm

    def traced_build(config):
        llm = original_build(config)
        role = ""
        # Infer role from model name heuristics
        model = getattr(config, "model", "") or ""
        if model:
            role = model
        return collector.wrap(llm, role=role)

    _factory.build_llm = traced_build

    # Also clear the LLM instance cache so next get_*_llm() creates fresh (traced) instances
    from app.services.llm_service import reset_llm_cache
    reset_llm_cache()

    yield collector

    # Restore original
    _factory.build_llm = original_build

    # Print the report
    report = collector.format_report()
    print(report)


# ---------------------------------------------------------------------------
# FileStore fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    """Isolated FileStore rooted in a temporary directory."""
    return FileStore(root=tmp_path)


@pytest.fixture
def seeded_store(store: FileStore) -> FileStore:
    """FileStore pre-populated with a session that has corpus + review."""
    from app.agents.session_corpus import SessionCorpus

    session = store.create_session("已有综述")
    session_id = session["id"]

    corpus = SessionCorpus()
    hits = seed_corpus_hits(3)
    for hit in hits:
        corpus.fetch_hits.append(hit)
        corpus.sources_md += f"\n\n## {hit['title']}\n\n{hit['snippet']}"
    store.save_corpus(session_id, corpus.to_dict())
    store.save_review_artifact(session_id, SEED_REVIEW_MARKDOWN)

    store._e2e_session_id = session_id  # type: ignore[attr-defined]
    store._e2e_corpus = corpus  # type: ignore[attr-defined]
    return store


# ---------------------------------------------------------------------------
# Store injection
# ---------------------------------------------------------------------------

_MODULES_WITH_GET_STORE = [
    "app.agents.literature_turn",
    "app.agents.agent_settings",
    "app.agents.session_corpus",
    "app.library.store",
    "app.library.reconcile",
    "app.library.migrate",
    "app.skills.citation_extractor",
]


def _patch_all_get_store(
    target: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.storage.backend as _backend

    monkeypatch.setattr(_backend, "_store", target)
    monkeypatch.setattr("app.storage.file_store.get_store", lambda: target)
    _getter = lambda: target
    for mod in _MODULES_WITH_GET_STORE:
        monkeypatch.setattr(f"{mod}.get_store", _getter, raising=False)


@pytest.fixture
def inject_store(
    store: FileStore, monkeypatch: pytest.MonkeyPatch, llm_trace: LLMTraceCollector
) -> FileStore:
    """Inject isolated FileStore + fast LLM config for non-review roles."""
    _patch_all_get_store(store, monkeypatch)
    _inject_fast_llm_config(store)
    return store


@pytest.fixture
def inject_seeded_store(
    seeded_store: FileStore, monkeypatch: pytest.MonkeyPatch, llm_trace: LLMTraceCollector
) -> FileStore:
    """Inject seeded FileStore + fast LLM config for non-review roles."""
    _patch_all_get_store(seeded_store, monkeypatch)
    _inject_fast_llm_config(seeded_store)
    return seeded_store


# ---------------------------------------------------------------------------
# Forced-clarify fixture — raises the Understand confidence threshold so the
# clarification sub-loop is guaranteed to emit a "clarification" event even
# when the user prompt would otherwise produce high-confidence routing.
# ---------------------------------------------------------------------------


@pytest.fixture
def force_clarify_store(
    inject_store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> FileStore:
    """inject_store + LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD=0.95.

    The threshold is read live via os.getenv at call time (see
    get_confidence_threshold in agent_settings), so setting the env var is
    sufficient to force clarification. Restored on teardown.
    """
    monkeypatch.setenv("LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD", "0.95")
    monkeypatch.setenv("LITPILOT_UNDERSTANDING_MAX_CLARIFICATION_ROUNDS", "2")
    return inject_store
