"""Non-sensitive deploy defaults bundled with the backend (Vercel seed fallback)."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTS_PATH = _BACKEND_ROOT / "config" / "deploy.defaults.json"

# Never load secrets from deploy.defaults.json — keys come from env / agent.json only.
SENSITIVE_SETTING_KEYS = frozenset(
    {
        "tavily_api_key",
        "jina_api_key",
        "llm_api_key",
        "llm_group_id",
    }
)


@lru_cache(maxsize=1)
def load_deploy_defaults_raw() -> dict[str, Any]:
    if not _DEFAULTS_PATH.is_file():
        return {}
    try:
        data = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def deploy_settings() -> dict[str, Any]:
    """Flat non-sensitive settings for v2 migration seeding.

    Sources (priority): env var → deploy.defaults.json → hardcoded fallback.
    """
    raw = load_deploy_defaults_raw()
    settings = dict(raw.get("settings") or {})

    settings["llm_model"] = (
        os.environ.get("OPENAI_MODEL")
        or str(settings.get("llm_model") or "")
    ).strip() or "deepseek-v4-pro"

    settings["orchestrator_model"] = (
        os.environ.get("ORCHESTRATOR_MODEL")
        or str(settings.get("orchestrator_model") or "")
    ).strip() or "deepseek-v4-flash"

    settings["llm_base_url"] = (
        os.environ.get("OPENAI_BASE_URL")
        or str(settings.get("llm_base_url") or "")
    ).strip() or "https://api.deepseek.com"

    settings["llm_provider"] = (
        os.environ.get("LLM_PROVIDER")
        or str(settings.get("llm_provider") or "")
    ).strip() or "openai"

    return settings


def deploy_credentials() -> list[dict[str, Any]]:
    raw = load_deploy_defaults_raw()
    items = raw.get("credentials")
    if not isinstance(items, list):
        return []
    return [dict(it) for it in items if isinstance(it, dict) and it.get("id") and it.get("key")]


def deploy_instances() -> list[dict[str, Any]]:
    raw = load_deploy_defaults_raw()
    items = raw.get("instances")
    if not isinstance(items, list):
        return []
    return [dict(it) for it in items if isinstance(it, dict) and it.get("id") and it.get("key")]


def defaults_path() -> Path:
    return _DEFAULTS_PATH
