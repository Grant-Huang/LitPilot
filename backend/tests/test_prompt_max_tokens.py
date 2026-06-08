"""Tests for per-prompt max_tokens resolution."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.prompt_registry import (
    clamp_prompt_params,
    default_max_tokens_for,
    prompt_max_tokens_param,
)
from app.agents.prompt_settings import get_prompt_max_tokens


def test_default_max_tokens_for_understanding() -> None:
    assert default_max_tokens_for("understanding_system_template") == 2000


def test_clamp_prompt_params_max_tokens() -> None:
    key = "understanding_system_template"
    param = prompt_max_tokens_param(key)
    out = clamp_prompt_params({param: 99999})
    assert out[param] <= 4000
    out2 = clamp_prompt_params({param: 50})
    assert out2[param] == 80


@pytest.mark.asyncio
async def test_get_prompt_max_tokens_uses_override() -> None:
    key = "assessor_system_template"
    param = prompt_max_tokens_param(key)
    with patch(
        "app.agents.prompt_settings.get_merged_settings",
        new=AsyncMock(return_value={param: 900}),
    ):
        assert await get_prompt_max_tokens(key) == 900


@pytest.mark.asyncio
async def test_get_prompt_max_tokens_orchestrator_narrate_builtin_default() -> None:
    with patch(
        "app.agents.prompt_settings.get_merged_settings",
        new=AsyncMock(return_value={}),
    ):
        tok = await get_prompt_max_tokens("narrate_search_after_template")
    assert tok == default_max_tokens_for("narrate_search_after_template")


@pytest.mark.asyncio
async def test_get_prompt_max_tokens_understanding_builtin_default() -> None:
    with patch(
        "app.agents.prompt_settings.get_merged_settings",
        new=AsyncMock(return_value={}),
    ):
        tok = await get_prompt_max_tokens("understanding_system_template")
    assert tok == 2000
