"""Explicit LLM instances for literature workflow.

- ``get_review_llm`` — review_main（能力页绑定）：综述分章撰写、矩阵、语料问答等「成稿」任务，用最全/主模型。
- ``get_planner_llm`` — orchestrator（能力页绑定）：路由、意图、阶段解说、检索精炼、网页摘要、文献结构化等编排任务。
"""
from __future__ import annotations

from app.agents.agent_settings import get_planner_llm_config, get_review_llm_config
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


async def get_llm() -> BaseLLM:
    """Deprecated alias — use ``get_review_llm`` or ``get_planner_llm`` explicitly."""
    return await get_review_llm()
