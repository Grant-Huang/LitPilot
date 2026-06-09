"""Clarification planner — generate 2–3 research direction options when Understand confidence is low."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.llm_json import parse_json_object
from app.agents.prompt_settings import get_clarify_system_prompt
from app.agents.search_aspects import SearchAspect
from app.core.think_stream import ThinkAccumulator, stream_llm_to_think
from app.llm.base import LLMMessage
from app.services.llm_service import get_planner_llm

_log = logging.getLogger(__name__)


@dataclass
class ClarificationOption:
    """单个澄清选项（格式与 UnderstandingResult 兼容）。"""

    option_id: str  # "opt_1", "opt_2", ...
    narration: str  # 3-5 句解说
    search_aspects: list[SearchAspect] = field(default_factory=list)


@dataclass
class ClarifyResult:
    """澄清阶段输出。"""

    clarification_prompt: str  # "请选择最符合您研究意图的方向："
    options: list[ClarificationOption]  # 2-3 个完整选项


async def stream_clarify_user_intent(
    user_message: str,
    understand_narration: str,
    *,
    think_acc: ThinkAccumulator | None = None,
) -> ClarifyResult:
    """生成澄清选项。

    Args:
        user_message: 原始用户输入
        understand_narration: Understand 阶段的解说（用于上下文）
        think_acc: 思考累加器（可选）

    Returns:
        ClarifyResult 包含 2–3 个完整的备选方案
    """
    try:
        llm = await get_planner_llm()
        clarify_system = await get_clarify_system_prompt()

        # 构造用户消息，含原始表述 + 系统初步理解
        user_prompt = f"""【用户原始表述】
{user_message}

【系统初步理解】
{understand_narration}

请生成 2–3 个具体的研究方向选项，每个选项应包含清晰的方向描述和完整的检索规划。"""

        # 流式调用 LLM
        content_buf = []

        async for event_name, event_data in stream_llm_to_think(
            llm,
            [LLMMessage(role="user", content=user_prompt)],
            system=clarify_system,
        ):
            if event_name == "text":
                content_buf.append(event_data.get("text", ""))
                if think_acc:
                    await think_acc.add(event_data.get("text", ""))

        full_response = "".join(content_buf)

        # 解析 JSON
        raw_json = parse_json_object(full_response)
        clarification_prompt = str(raw_json.get("clarification_prompt", "请选择研究方向：")).strip()
        options_raw = raw_json.get("options", [])

        options: list[ClarificationOption] = []
        for opt_data in options_raw:
            if not isinstance(opt_data, dict):
                continue

            option_id = str(opt_data.get("option_id", "")).strip()
            narration = str(opt_data.get("narration", "")).strip()

            # 解析 search_aspects
            aspects_raw = opt_data.get("search_aspects", [])
            search_aspects = []
            for aspect_data in aspects_raw:
                if isinstance(aspect_data, dict):
                    # 这里可以用 SearchAspect.from_dict() 如果有的话
                    # 否则构建简单的 dict
                    search_aspects.append(aspect_data)

            if option_id and narration:
                options.append(
                    ClarificationOption(
                        option_id=option_id,
                        narration=narration,
                        search_aspects=search_aspects,
                    )
                )

        if not options:
            # Fallback：至少返回一个通用选项
            options = [
                ClarificationOption(
                    option_id="opt_1",
                    narration="基于用户表述的默认方向",
                    search_aspects=[],
                )
            ]

        return ClarifyResult(
            clarification_prompt=clarification_prompt,
            options=options,
        )

    except Exception as e:
        _log.exception("Failed to clarify user intent: %s", e)
        # Fallback
        return ClarifyResult(
            clarification_prompt="请重新描述您的研究意图：",
            options=[
                ClarificationOption(
                    option_id="opt_1",
                    narration="基于用户表述的默认方向",
                    search_aspects=[],
                )
            ],
        )
