from unittest.mock import AsyncMock, patch

import pytest

from app.services.llm_service import get_planner_llm, get_review_llm


@pytest.mark.asyncio
async def test_review_and_planner_use_distinct_configs() -> None:
    review_cfg = {
        "provider": "openai",
        "api_key": "review-key",
        "model": "Review-Max",
        "base_url": "https://review.example/v1",
        "extra": None,
    }
    planner_cfg = {
        "provider": "minimax_cn",
        "api_key": "plan-key",
        "model": "Planner-Fast",
        "base_url": "https://plan.example/v1",
        "extra": None,
    }

    with (
        patch(
            "app.services.llm_service.get_review_llm_config",
            new_callable=AsyncMock,
            return_value=review_cfg,
        ),
        patch(
            "app.services.llm_service.get_planner_llm_config",
            new_callable=AsyncMock,
            return_value=planner_cfg,
        ),
        patch("app.services.llm_service.build_llm") as build,
    ):
        built: list = []

        def _capture(cfg):
            built.append(cfg)
            return object()

        build.side_effect = _capture
        await get_review_llm()
        await get_planner_llm()

    assert built[0].model == "Review-Max"
    assert built[1].model == "Planner-Fast"
    assert built[0].api_key == "review-key"
    assert built[1].api_key == "plan-key"
