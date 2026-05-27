"""Agent settings from file store + environment."""
from __future__ import annotations

from typing import Any

from app.storage.file_store import get_store


async def get_merged_settings() -> dict[str, Any]:
    return get_store().get_agent_settings_merged()


async def get_tavily_api_key() -> str:
    return (await get_merged_settings()).get("tavily_api_key") or ""


async def get_jina_api_key() -> str:
    return (await get_merged_settings()).get("jina_api_key") or ""


async def get_fetch_parallel() -> int:
    n = int((await get_merged_settings()).get("fetch_parallel") or 3)
    return max(1, min(n, 8))


async def get_fetch_timeout_sec() -> float:
    t = float((await get_merged_settings()).get("fetch_timeout_sec") or 45)
    return max(10.0, min(t, 120.0))


TAVILY_MAX_RESULTS_CAP = 80


async def get_tavily_max_results() -> int:
    n = int((await get_merged_settings()).get("tavily_max_results") or 8)
    return max(1, min(n, TAVILY_MAX_RESULTS_CAP))


MAX_FETCH_URLS_CAP = 50


async def get_max_fetch_urls() -> int:
    n = int((await get_merged_settings()).get("max_fetch_urls") or 5)
    return max(1, min(n, MAX_FETCH_URLS_CAP))


async def get_literature_source_mode() -> str:
    from app.agents.literature_source import normalize_literature_source_mode

    raw = (await get_merged_settings()).get("literature_source_mode") or "merge"
    return normalize_literature_source_mode(str(raw))


async def get_tavily_retry_count() -> int:
    n = int((await get_merged_settings()).get("tavily_retry_count") or 0)
    return max(0, min(n, 3))


async def get_fetch_retry_count() -> int:
    n = int((await get_merged_settings()).get("fetch_retry_count") or 0)
    return max(0, min(n, 3))


async def get_fetch_retry_delay_ms() -> int:
    n = int((await get_merged_settings()).get("fetch_retry_delay_ms") or 500)
    return max(0, min(n, 5000))


async def is_plan_confirm_required() -> bool:
    return bool((await get_merged_settings()).get("plan_confirm"))


async def get_citation_format() -> str:
    from app.skills.citation_extractor import normalize_citation_format

    return normalize_citation_format((await get_merged_settings()).get("citation_format"))


async def get_review_system_prompt_template() -> str | None:
    raw = (await get_merged_settings()).get("review_system_prompt_template")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


async def get_use_llm_planner() -> bool:
    return bool((await get_merged_settings()).get("use_llm_planner", True))


async def get_think_mode() -> str:
    raw = str((await get_merged_settings()).get("think_mode") or "lite").strip().lower()
    if raw in ("off", "lite", "full"):
        return raw
    return "lite"


async def get_think_use_reasoning() -> bool:
    return bool((await get_merged_settings()).get("think_use_reasoning", False))


async def get_think_model() -> str:
    return str((await get_merged_settings()).get("think_model") or "").strip()


async def get_think_max_tokens() -> int:
    n = int((await get_merged_settings()).get("think_max_tokens_per_phase") or 280)
    return max(80, min(n, 500))


async def get_llm_config() -> dict[str, Any]:
    from app.llm.factory import PROVIDER_REGISTRY

    s = await get_merged_settings()
    provider = s.get("llm_provider") or "openai"
    meta = PROVIDER_REGISTRY.get(provider, PROVIDER_REGISTRY["openai"])
    extra: dict[str, str] = {}
    group_id = (s.get("llm_group_id") or "").strip()
    if group_id:
        extra["group_id"] = group_id
    return {
        "provider": provider,
        "api_key": s.get("llm_api_key") or "",
        "model": s.get("llm_model") or meta.get("default_model", "gpt-4o-mini"),
        "base_url": s.get("llm_base_url") or meta.get("default_base_url"),
        "extra": extra or None,
    }
