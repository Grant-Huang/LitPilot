"""Explicit LLM instances for literature workflow.

- ``get_review_llm`` — review_main：综述分章撰写、矩阵、语料问答等「成稿」任务。
- ``get_planner_llm`` — orchestrator：阶段解说与 Checkpoint A 理解路由。
- ``get_router_llm`` / ``get_search_llm`` / ``get_assessor_llm`` / ``get_pipeline_llm`` —
  提示词分组实例（未单独绑定时回退 orchestrator）。
"""
from __future__ import annotations

import json

from app.agents.agent_settings import (
    get_assessor_llm_config,
    get_pipeline_llm_config,
    get_planner_llm_config,
    get_review_llm_config,
    get_router_llm_config,
    get_search_llm_config,
)
from app.llm.base import BaseLLM, LLMConfig
from app.llm.factory import build_llm

# 按配置签名缓存 LLM 实例：配置不变时复用同一实例（含其内部连接池），
# 避免每次调用重建客户端；配置变更（新签名）自动重建。
_llm_cache: dict[tuple, BaseLLM] = {}


def _cfg_key(cfg: dict) -> tuple:
    extra = cfg.get("extra") or {}
    return (
        cfg["provider"],
        cfg["api_key"],
        cfg.get("model"),
        cfg.get("base_url"),
        json.dumps(extra, sort_keys=True, ensure_ascii=False),
    )


def reset_llm_cache() -> None:
    """清空实例缓存（测试 / 配置热更新时调用）。"""
    _llm_cache.clear()


def _build_from_cfg(cfg: dict) -> BaseLLM:
    key = _cfg_key(cfg)
    inst = _llm_cache.get(key)
    if inst is None:
        inst = build_llm(
            LLMConfig(
                provider=cfg["provider"],
                api_key=cfg["api_key"],
                model=cfg["model"],
                base_url=cfg.get("base_url"),
                extra=cfg.get("extra"),
            )
        )
        _llm_cache[key] = inst
    return inst


async def get_review_llm() -> BaseLLM:
    return _build_from_cfg(await get_review_llm_config())


async def get_planner_llm() -> BaseLLM:
    return _build_from_cfg(await get_planner_llm_config())


async def get_router_llm() -> BaseLLM:
    return _build_from_cfg(await get_router_llm_config())


async def get_search_llm() -> BaseLLM:
    return _build_from_cfg(await get_search_llm_config())


async def get_assessor_llm() -> BaseLLM:
    return _build_from_cfg(await get_assessor_llm_config())


async def get_pipeline_llm() -> BaseLLM:
    return _build_from_cfg(await get_pipeline_llm_config())


async def get_llm() -> BaseLLM:
    """Deprecated alias — use ``get_review_llm`` or ``get_planner_llm`` explicitly."""
    return await get_review_llm()
