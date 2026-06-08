"""第三档：LLM 实例缓存与 SSE 心跳测试。"""
from __future__ import annotations

import asyncio

import pytest

from app.services import llm_service
from app.tasks import literature_tasks as lt
from app.tasks.task_store import TaskRecord


def test_build_from_cfg_reuses_instance_for_same_config(monkeypatch) -> None:
    llm_service.reset_llm_cache()
    calls: list = []

    def _fake_build(cfg):
        calls.append(cfg)
        return object()

    monkeypatch.setattr(llm_service, "build_llm", _fake_build)
    cfg = {
        "provider": "minimax_cn",
        "api_key": "k",
        "model": "m",
        "base_url": None,
        "extra": None,
    }
    a = llm_service._build_from_cfg(cfg)
    b = llm_service._build_from_cfg(dict(cfg))
    assert a is b
    assert len(calls) == 1


def test_build_from_cfg_rebuilds_on_config_change(monkeypatch) -> None:
    llm_service.reset_llm_cache()
    calls: list = []
    monkeypatch.setattr(
        llm_service, "build_llm", lambda c: calls.append(c) or object()
    )
    cfg = {
        "provider": "minimax_cn",
        "api_key": "k",
        "model": "m",
        "base_url": None,
        "extra": None,
    }
    a = llm_service._build_from_cfg(cfg)
    c = llm_service._build_from_cfg({**cfg, "model": "other"})
    assert a is not c
    assert len(calls) == 2


class _RunningStore:
    def get_task(self, task_id: str):
        return TaskRecord(id=task_id, session_id="s", message="m", fetch_urls=[], status="running")

    def list_events(self, task_id: str, since: int = 0):
        return []


async def test_heartbeat_emitted_when_idle(monkeypatch) -> None:
    monkeypatch.setattr(lt, "HEARTBEAT_SEC", 0.0)
    monkeypatch.setattr(lt, "STREAM_POLL_SEC", 0.01)
    reg = lt.LiteratureTaskRegistry.__new__(lt.LiteratureTaskRegistry)
    reg._store = _RunningStore()
    reg._event_signals = {}

    gen = reg.iter_stream("tid", since=0)
    try:
        line = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        assert line == ": keepalive\n\n"
    finally:
        await gen.aclose()
