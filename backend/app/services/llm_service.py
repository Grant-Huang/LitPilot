from __future__ import annotations

from app.agents.agent_settings import get_llm_config, get_orchestrator_model
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


async def get_llm() -> BaseLLM:
    return _build_from_cfg(await get_llm_config())


async def get_planner_llm() -> BaseLLM:
    cfg = await get_llm_config()
    override = await get_orchestrator_model()
    if override:
        cfg = {**cfg, "model": override}
    return _build_from_cfg(cfg)
