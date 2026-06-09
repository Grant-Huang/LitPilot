"""Agent settings from file store + environment — with short-TTL memory cache and
serverless cold-start file fallback."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any


from app.agents.tools.search_hits import ACADEMIC_SEARCH_DOMAINS, DEFAULT_EXCLUDE_DOMAINS

from app.storage.file_store import get_store

# 内存 TTL 缓存：避免同一进程/请求内重复 Turso 调用
_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_TS: float = 0.0
_SETTINGS_TTL_SEC = float(os.getenv("LITPILOT_SETTINGS_CACHE_SEC", "15").strip() or "15")

# 文件级 fallback 缓存：Vercel serverless 冷启动时 /tmp 可能存活 5~15 分钟
_SETTINGS_FILE = os.getenv(
    "LITPILOT_SETTINGS_CACHE_FILE",
    "/tmp/litpilot_settings_cache.json",
)
_SETTINGS_FILE_TTL_SEC = float(
    os.getenv("LITPILOT_SETTINGS_FILE_TTL_SEC", "300").strip() or "300"
)


def _clear_settings_cache() -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TS
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_TS = 0.0


def _clear_all_caches() -> None:
    """清空内存缓存 + 删除文件缓存（保存设置时调用）。"""
    _clear_settings_cache()
    _remove_file_cache()


def _remove_file_cache() -> None:
    try:
        if os.path.isfile(_SETTINGS_FILE):
            os.remove(_SETTINGS_FILE)
    except OSError:
        pass


def _load_file_cache() -> dict[str, Any] | None:
    try:
        if not os.path.isfile(_SETTINGS_FILE):
            return None
        mtime = os.path.getmtime(_SETTINGS_FILE)
        if time.time() - mtime >= _SETTINGS_FILE_TTL_SEC:
            _remove_file_cache()
            return None
        with open(_SETTINGS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_file_cache(data: dict[str, Any]) -> None:
    try:
        with open(_SETTINGS_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


async def get_merged_settings() -> dict[str, Any]:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TS
    now = time.monotonic()
    # 1) 进程级内存缓存（命中即返回）
    if _SETTINGS_CACHE is not None and now - _SETTINGS_CACHE_TS < _SETTINGS_TTL_SEC:
        return _SETTINGS_CACHE
    # 2) 文件级 fallback 缓存（serverless 冷启动存活）
    file_data = _load_file_cache()
    if file_data is not None:
        _SETTINGS_CACHE = file_data
        _SETTINGS_CACHE_TS = now
        return _SETTINGS_CACHE
    # 3) 真实 Turso / File store 查询（asyncio.to_thread 防止阻塞事件循环）
    store = get_store()
    _SETTINGS_CACHE = await asyncio.to_thread(store.get_agent_settings_merged)
    _SETTINGS_CACHE_TS = now
    _write_file_cache(_SETTINGS_CACHE)
    return _SETTINGS_CACHE





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





MAX_FETCH_URLS_CAP = 50





async def get_max_fetch_urls() -> int:

    n = int((await get_merged_settings()).get("max_fetch_urls") or 5)

    return max(1, min(n, MAX_FETCH_URLS_CAP))










async def get_search_retry_count() -> int:

    n = int((await get_merged_settings()).get("search_retry_count") or 3)

    return max(0, min(n, 3))





async def get_fetch_retry_count() -> int:

    n = int((await get_merged_settings()).get("fetch_retry_count") or 0)

    return max(0, min(n, 3))





async def get_fetch_retry_delay_ms() -> int:

    n = int((await get_merged_settings()).get("fetch_retry_delay_ms") or 500)

    return max(0, min(n, 5000))










async def get_citation_format() -> str:

    from app.skills.citation_extractor import normalize_citation_format



    return normalize_citation_format((await get_merged_settings()).get("citation_format"))







async def get_use_llm_planner() -> bool:

    return bool((await get_merged_settings()).get("use_llm_planner", True))







async def get_orchestrator_model() -> str:

    """Planner/orchestrator model name (v2 orchestrator instance or legacy override)."""

    return str((await get_merged_settings()).get("planner_llm_model") or "").strip() or str(

        (await get_merged_settings()).get("orchestrator_model") or ""

    ).strip()










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


async def get_orchestrator_use_reasoning() -> bool:
    """规划模型推理开关（orchestrator_use_reasoning），控制 DeepSeek thinking 模式。"""
    return bool((await get_merged_settings()).get("orchestrator_use_reasoning", False))


def _llm_cfg_from_flat(
    s: dict[str, Any],
    *,
    prefix: str = "",
    thinking: str | None = None,
) -> dict[str, Any]:
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
    if thinking:
        extra["thinking"] = thinking
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
    s = await get_merged_settings()
    thinking = "enabled" if s.get("orchestrator_use_reasoning") else None
    return _llm_cfg_from_flat(s, prefix="planner_llm", thinking=thinking)


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


# --- Understanding & Clarification Settings ---

async def get_confidence_threshold() -> float:
    """Understand 阶段的置信度阈值 [0.0, 1.0]。
    置信度 ≥ 此阈值时直接进入搜索，否则进入澄清阶段。"""
    val = os.getenv("LITPILOT_UNDERSTANDING_CONFIDENCE_THRESHOLD", "0.7").strip()
    try:
        threshold = float(val)
        return max(0.0, min(1.0, threshold))  # Clamp to [0.0, 1.0]
    except ValueError:
        return 0.7


async def get_max_clarification_rounds() -> int:
    """最多澄清轮数，避免死循环。"""
    val = os.getenv("LITPILOT_UNDERSTANDING_MAX_CLARIFICATION_ROUNDS", "2").strip()
    try:
        return max(1, int(val))
    except ValueError:
        return 2

