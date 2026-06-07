"""Explicit LLM instances for literature workflow.

- ``get_review_llm`` — review_main：综述分章撰写、矩阵、语料问答等「成稿」任务。
- ``get_planner_llm`` — orchestrator：阶段解说与 Checkpoint A 理解路由。
- ``get_router_llm`` / ``get_search_llm`` / ``get_assessor_llm`` / ``get_pipeline_llm`` —
  提示词分组实例（未单独绑定时回退 orchestrator）。
"""
from __future__ import annotations

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


def _build_from_cfg(cfg: dict) -> BaseLLM:
    return build_llm(
        LLMConfig(
            provider=cfg["provider"],
            api_key=cfg["api_key"],
            model=cfg["model"],
            base_url=cfg.get("base_url"),
            extra=cfg.get("extra"),
        )
    )


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
