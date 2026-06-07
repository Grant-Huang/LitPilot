"""Async accessors for configurable prompt templates from merged settings."""
from __future__ import annotations

from app.agents.agent_settings import get_merged_settings
from app.agents.prompt_registry import (
    NARRATE_CHECKPOINT_KEYS,
    PROMPT_SPECS,
    clamp_prompt_max_tokens_value,
    default_max_tokens_for,
    prompt_max_tokens_param,
    resolve_prompt_template,
)


async def _template_override(key: str) -> str | None:
    raw = (await get_merged_settings()).get(key)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


async def get_resolved_prompt(key: str) -> str:
    return resolve_prompt_template(key, await _template_override(key))


async def get_understanding_system_prompt() -> str:
    return await get_resolved_prompt("understanding_system_template")


async def get_narrate_checkpoint_system_prompt(checkpoint: str) -> str | None:
    param_key = NARRATE_CHECKPOINT_KEYS.get(checkpoint)
    if not param_key:
        return None
    return await get_resolved_prompt(param_key)


async def get_router_system_prompt() -> str:
    return await get_resolved_prompt("router_system_template")


async def get_intent_router_system_prompt() -> str:
    return await get_resolved_prompt("intent_router_system_template")


async def get_search_refiner_system_prompt() -> str:
    return await get_resolved_prompt("search_refiner_system_template")


async def get_assessor_system_prompt() -> str:
    return await get_resolved_prompt("assessor_system_template")


async def get_search_expansion_system_prompt() -> str:
    return await get_resolved_prompt("search_expansion_system_template")


async def get_query_corpus_system_prompt() -> str:
    return await get_resolved_prompt("query_corpus_system_template")


async def get_section_system_prompt(*, is_refine: bool) -> str:
    key = "section_refine_system_template" if is_refine else "section_system_template"
    return await get_resolved_prompt(key)


async def get_matrix_system_prompt() -> str:
    return await get_resolved_prompt("matrix_system_template")


async def get_attribute_system_prompt() -> str:
    return await get_resolved_prompt("attribute_system_template")


async def get_summary_system_prompt() -> str:
    return await get_resolved_prompt("summary_system_template")


async def get_prompt_max_tokens(key: str) -> int:
    """Resolved max_tokens for a prompt template key (per-prompt override or group default)."""
    param = prompt_max_tokens_param(key)
    raw = (await get_merged_settings()).get(param)
    if raw is not None and str(raw).strip() != "":
        return clamp_prompt_max_tokens_value(key, raw)
    return default_max_tokens_for(key)


def list_prompt_template_keys() -> tuple[str, ...]:
    return tuple(PROMPT_SPECS.keys())
