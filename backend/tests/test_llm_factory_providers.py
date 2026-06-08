"""新增 deepseek / qwen 一等 provider 支持。"""
from __future__ import annotations

import pytest

from app.llm.base import LLMConfig
from app.llm.factory import PROVIDER_REGISTRY, build_llm
from app.llm.openai_llm import OpenAILLM


@pytest.mark.parametrize(
    "provider,expect_base,expect_model",
    [
        ("deepseek", "https://api.deepseek.com", "deepseek-chat"),
        ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ],
)
def test_registry_has_new_providers(provider, expect_base, expect_model) -> None:
    meta = PROVIDER_REGISTRY[provider]
    assert meta["default_base_url"] == expect_base
    assert meta["default_model"] == expect_model
    assert meta["requires_api_key"] is True


@pytest.mark.parametrize("provider", ["deepseek", "qwen"])
def test_build_llm_routes_new_providers_to_openai_compatible(provider) -> None:
    llm = build_llm(LLMConfig(provider=provider, api_key="k"))
    assert isinstance(llm, OpenAILLM)


@pytest.mark.parametrize(
    "provider,expect_base",
    [
        ("deepseek", "https://api.deepseek.com"),
        ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ],
)
def test_build_llm_applies_default_base_url(provider, expect_base) -> None:
    cfg = LLMConfig(provider=provider, api_key="k")
    build_llm(cfg)
    assert cfg.base_url == expect_base


@pytest.mark.parametrize(
    "provider,expect_model",
    [
        ("deepseek", "deepseek-chat"),
        ("qwen", "qwen-plus"),
    ],
)
def test_openai_llm_default_model_for_new_providers(provider, expect_model) -> None:
    llm = OpenAILLM(LLMConfig(provider=provider, api_key="k"))
    assert llm._default_model() == expect_model
