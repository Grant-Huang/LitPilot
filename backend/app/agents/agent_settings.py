"""Agent settings from file store + environment."""

from __future__ import annotations

import os

from typing import Any



from app.agents.tools.search_hits import ACADEMIC_SEARCH_DOMAINS, DEFAULT_EXCLUDE_DOMAINS

from app.storage.file_store import get_store





async def get_merged_settings() -> dict[str, Any]:

    return get_store().get_agent_settings_merged()





async def get_brave_api_key() -> str:

    s = await get_merged_settings()

    return str(s.get("brave_api_key") or s.get("web_search_api_key") or "")





async def get_web_search_api_key() -> str:

    s = await get_merged_settings()

    provider = str(s.get("search_provider") or "multi_academic").strip().lower()

    if provider == "brave":

        return str(s.get("brave_api_key") or s.get("web_search_api_key") or "")

    if provider == "tavily":

        return str(s.get("web_search_api_key") or "")

    return ""





async def get_s2_api_key() -> str:
    """Semantic Scholar Graph API key (settings credential or SEMANTIC_SCHOLAR_API_KEY)."""
    s = await get_merged_settings()
    key = str(s.get("s2_api_key") or "").strip()
    if key:
        return key
    return str(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")).strip()


async def get_fetch_api_key() -> str:

    """API key for the active web_fetch backend (empty when native)."""

    if await get_web_fetch_provider() != "jina":

        return ""

    return str((await get_merged_settings()).get("fetch_api_key") or "")


async def get_jina_reader_api_key() -> str:
    """Jina Reader key for native-pipeline Cloudflare fallback (optional)."""
    return str((await get_merged_settings()).get("fetch_api_key") or "").strip()





async def get_web_search_provider() -> str:

    from app.agents.tools.web_providers import normalize_search_provider



    raw = (await get_merged_settings()).get("search_provider")

    return normalize_search_provider(str(raw) if raw else None)





async def get_web_fetch_provider() -> str:

    from app.agents.tools.web_providers import normalize_fetch_provider



    raw = (await get_merged_settings()).get("fetch_provider")

    return normalize_fetch_provider(str(raw) if raw else None)





async def get_pdf_extract_backend() -> str:

    from app.agents.tools.pdf_text import normalize_pdf_extract_backend



    raw = (await get_merged_settings()).get("pdf_extract_backend")

    return normalize_pdf_extract_backend(str(raw) if raw else None)





async def get_fetch_parallel() -> int:

    n = int((await get_merged_settings()).get("fetch_parallel") or 3)

    return max(1, min(n, 8))





async def get_fetch_timeout_sec() -> float:

    t = float((await get_merged_settings()).get("fetch_timeout_sec") or 45)

    return max(10.0, min(t, 120.0))





SEARCH_MAX_RESULTS_CAP = 80





async def get_search_max_results() -> int:

    n = int((await get_merged_settings()).get("search_max_results") or 20)

    return max(1, min(n, SEARCH_MAX_RESULTS_CAP))





SEARCH_PARALLEL_CAP = 4





async def get_search_parallel() -> int:

    n = int((await get_merged_settings()).get("search_parallel") or 1)

    return max(1, min(n, SEARCH_PARALLEL_CAP))





async def get_merge_search_budget() -> str:

    from app.agents.literature_source import normalize_merge_search_budget

    raw = (await get_merged_settings()).get("merge_search_budget") or "full"

    return normalize_merge_search_budget(str(raw))





MAX_FETCH_URLS_CAP = 50





async def get_max_fetch_urls() -> int:

    n = int((await get_merged_settings()).get("max_fetch_urls") or 5)

    return max(1, min(n, MAX_FETCH_URLS_CAP))





async def get_literature_source_mode() -> str:

    from app.agents.literature_source import normalize_literature_source_mode



    raw = (await get_merged_settings()).get("literature_source_mode") or "merge"

    return normalize_literature_source_mode(str(raw))





async def get_search_retry_count() -> int:

    n = int((await get_merged_settings()).get("search_retry_count") or 3)

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


async def get_orchestrator_use_reasoning() -> bool:
    """Reasoning mode is disabled (hard-coded off)."""
    return False





async def get_orchestrator_model() -> str:

    """Planner/orchestrator model name (v2 orchestrator instance or legacy override)."""

    return str((await get_merged_settings()).get("planner_llm_model") or "").strip() or str(

        (await get_merged_settings()).get("orchestrator_model") or ""

    ).strip()





async def get_orchestrator_max_tokens() -> int:

    n = int(

        (await get_merged_settings()).get("orchestrator_max_tokens_per_phase") or 280

    )

    return max(80, min(n, 500))





async def get_search_include_domains() -> tuple[str, ...]:

    raw = (await get_merged_settings()).get("search_include_domains") or ()

    if isinstance(raw, (list, tuple)):

        domains = tuple(str(d).strip() for d in raw if str(d).strip())

        return domains if domains else ACADEMIC_SEARCH_DOMAINS

    return ACADEMIC_SEARCH_DOMAINS





async def get_search_exclude_domains() -> tuple[str, ...]:

    raw = (await get_merged_settings()).get("search_exclude_domains") or ()

    if isinstance(raw, (list, tuple)):

        domains = tuple(str(d).strip() for d in raw if str(d).strip())

        return domains if domains else DEFAULT_EXCLUDE_DOMAINS

    return DEFAULT_EXCLUDE_DOMAINS





async def get_search_depth() -> str:

    raw = str((await get_merged_settings()).get("search_depth") or "advanced").strip().lower()

    return raw if raw in ("basic", "advanced") else "advanced"





async def get_search_enforce_domain_filter() -> bool:

    return bool((await get_merged_settings()).get("search_enforce_domain_filter", True))





async def get_search_enable_junk_filter() -> bool:

    return bool((await get_merged_settings()).get("search_enable_junk_filter", True))





async def get_max_source_chars() -> int:

    n = int((await get_merged_settings()).get("max_source_chars") or 14_000)

    return max(2_000, min(n, 50_000))





async def get_enable_paper_attributes() -> bool:

    return bool((await get_merged_settings()).get("enable_paper_attributes", True))





async def get_enable_query_expansion() -> bool:

    return bool((await get_merged_settings()).get("enable_query_expansion", True))





async def get_search_expansion_count() -> int:

    n = int((await get_merged_settings()).get("search_expansion_count") or 3)

    return max(1, min(n, 4))





async def get_outline_mode() -> str:

    raw = str((await get_merged_settings()).get("outline_mode") or "lite").strip().lower()

    if raw in ("off", "lite", "full"):

        return raw

    return "lite"





async def get_post_refine_mode() -> str:

    raw = str((await get_merged_settings()).get("post_refine_mode") or "lite").strip().lower()

    if raw in ("off", "lite"):

        return raw

    return "lite"





def _llm_cfg_from_flat(s: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:

    from app.llm.factory import PROVIDER_REGISTRY



    if prefix:

        provider = s.get(f"{prefix}_provider") or "openai"

        api_key = s.get(f"{prefix}_api_key") or ""

        model = s.get(f"{prefix}_model") or ""

        base_url = s.get(f"{prefix}_base_url") or ""

        group_id = (s.get(f"{prefix}_group_id") or "").strip()

    else:

        provider = s.get("llm_provider") or "openai"

        api_key = s.get("llm_api_key") or ""

        model = s.get("llm_model") or ""

        base_url = s.get("llm_base_url") or ""

        group_id = (s.get("llm_group_id") or "").strip()



    meta = PROVIDER_REGISTRY.get(provider, PROVIDER_REGISTRY["openai"])

    extra: dict[str, str] = {}

    if group_id:

        extra["group_id"] = group_id

    return {

        "provider": provider,

        "api_key": api_key,

        "model": model or meta.get("default_model", "gpt-4o-mini"),

        "base_url": base_url or meta.get("default_base_url"),

        "extra": extra or None,

    }





async def get_review_llm_config() -> dict[str, Any]:

    """review_main 能力绑定的主模型（综述撰写、矩阵、语料问答）。"""

    return _llm_cfg_from_flat(await get_merged_settings())





async def get_planner_llm_config() -> dict[str, Any]:

    """orchestrator 能力绑定的编排模型（理解、解说、检索精炼、抓取摘要、结构化等）。"""

    return _llm_cfg_from_flat(await get_merged_settings(), prefix="planner_llm")


async def get_router_llm_config() -> dict[str, Any]:
    return _llm_cfg_from_flat(await get_merged_settings(), prefix="router_llm")


async def get_search_llm_config() -> dict[str, Any]:
    return _llm_cfg_from_flat(await get_merged_settings(), prefix="search_llm")


async def get_assessor_llm_config() -> dict[str, Any]:
    return _llm_cfg_from_flat(await get_merged_settings(), prefix="assessor_llm")


async def get_pipeline_llm_config() -> dict[str, Any]:
    return _llm_cfg_from_flat(await get_merged_settings(), prefix="pipeline_llm")


async def get_llm_config() -> dict[str, Any]:

    """Backward-compatible alias for review_main LLM config."""

    return await get_review_llm_config()

