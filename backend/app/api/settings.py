from __future__ import annotations

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.tavily_key import looks_like_tavily_api_key, tavily_key_hint
from app.agents.tools.tavily_search import tavily_search
from app.core.response import err, ok
from app.agents.literature_source import normalize_literature_source_mode
from app.skills.citation_extractor import normalize_citation_format
from app.storage.file_store import get_store

router = APIRouter(prefix="/settings", tags=["settings"])


class AgentSettingsBody(BaseModel):
    tavily_api_key: str | None = None
    jina_api_key: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_group_id: str | None = None
    fetch_parallel: int | None = None
    fetch_timeout_sec: float | None = None
    tavily_max_results: int | None = None
    max_fetch_urls: int | None = None
    literature_source_mode: str | None = None
    tavily_retry_count: int | None = None
    fetch_retry_count: int | None = None
    fetch_retry_delay_ms: int | None = None
    plan_confirm: bool | None = None
    citation_format: str | None = None
    use_llm_planner: bool | None = None
    think_mode: str | None = None
    think_use_reasoning: bool | None = None
    think_model: str | None = None
    think_max_tokens_per_phase: int | None = None


def _agent_settings_response(merged: dict) -> dict:
    safe = dict(merged)
    safe["has_tavily"] = bool(merged.get("tavily_api_key"))
    safe["has_jina"] = bool(merged.get("jina_api_key"))
    provider = merged.get("llm_provider") or "openai"
    safe["has_llm"] = bool(merged.get("llm_api_key")) or provider == "ollama"
    safe["llm_group_id"] = merged.get("llm_group_id") or ""
    for k in ("tavily_api_key", "jina_api_key", "llm_api_key"):
        if safe.get(k):
            safe[k] = "***" + str(merged[k])[-4:]
    return safe


@router.get("/agent")
async def get_agent_settings():
    merged = get_store().get_agent_settings_merged()
    return ok(_agent_settings_response(merged))


@router.post("/agent")
async def save_agent_settings(body: AgentSettingsBody):
    partial = body.model_dump(exclude_none=True)
    if "citation_format" in partial:
        partial["citation_format"] = normalize_citation_format(partial["citation_format"])
    if "tavily_max_results" in partial:
        partial["tavily_max_results"] = max(1, min(int(partial["tavily_max_results"]), 20))
    if "max_fetch_urls" in partial:
        partial["max_fetch_urls"] = max(1, min(int(partial["max_fetch_urls"]), 20))
    if "literature_source_mode" in partial:
        partial["literature_source_mode"] = normalize_literature_source_mode(
            partial["literature_source_mode"]
        )
    if "tavily_retry_count" in partial:
        partial["tavily_retry_count"] = max(0, min(int(partial["tavily_retry_count"]), 3))
    if "fetch_retry_count" in partial:
        partial["fetch_retry_count"] = max(0, min(int(partial["fetch_retry_count"]), 3))
    if "fetch_retry_delay_ms" in partial:
        partial["fetch_retry_delay_ms"] = max(
            0, min(int(partial["fetch_retry_delay_ms"]), 5000)
        )
    if "tavily_api_key" in partial:
        hint = tavily_key_hint(partial["tavily_api_key"])
        if hint:
            return err(hint)
    if "think_mode" in partial:
        mode = str(partial["think_mode"]).strip().lower()
        if mode not in ("off", "lite", "full"):
            return err("think_mode 须为 off、lite 或 full")
        partial["think_mode"] = mode
    if "think_max_tokens_per_phase" in partial:
        partial["think_max_tokens_per_phase"] = max(
            80, min(int(partial["think_max_tokens_per_phase"]), 500)
        )
    saved = get_store().save_agent_settings(partial)
    return ok(_agent_settings_response(saved), message="设置已保存")


class TestTavilyBody(BaseModel):
    api_key: str | None = None
    query: str = "transformer attention paper arxiv"


@router.post("/agent/test-tavily")
async def test_tavily(body: TestTavilyBody):
    key = body.api_key or get_store().get_agent_settings_merged().get("tavily_api_key")
    if not key:
        return err("未配置 Tavily API Key")
    hint = tavily_key_hint(key)
    if hint:
        return err(hint)
    try:
        data = await tavily_search(key, body.query, max_results=3)
        hits = len(data.get("results") or [])
        return ok({"hits": hits, "answer_preview": str(data.get("answer") or "")[:200]})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return err(
                "Tavily 返回 401 Unauthorized：Key 无效、已撤销或已过期。"
                "请在 https://tavily.com 重新生成 tvly- 开头的 API Key，"
                "在设置页粘贴并保存后点击「测试 Tavily」。"
            )
        return err(f"Tavily 请求失败: {e}")
    except httpx.HTTPError as e:
        return err(f"Tavily 请求失败: {e}")
