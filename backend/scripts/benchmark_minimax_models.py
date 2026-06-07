#!/usr/bin/env python3
"""Live benchmark: MiniMax model latency (TTFT + total + throughput).

Usage:
  OPENAI_API_KEY=sk-... python scripts/benchmark_minimax_models.py
  python scripts/benchmark_minimax_models.py --api-key sk-... --rounds 5
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.agents.agent_settings import get_merged_settings
from app.llm.base import LLMConfig, LLMMessage
from app.llm.minimax_cn_llm import MinimaxCNLLM

MODELS = ("MiniMax-M2.7-highspeed", "MiniMax-M3")
PROMPT = (
    "用三句话概括：大语言模型在工业多智能体调度中的主要应用与挑战。"
    "直接回答，不要展开推理过程。"
)
SYSTEM = "你是简洁的学术助手。"
MAX_TOKENS = 256


@dataclass
class RoundStats:
    ttft_ms: float | None
    total_ms: float
    out_chars: int
    error: str | None = None


async def stream_round(llm: MinimaxCNLLM) -> RoundStats:
    t0 = time.perf_counter()
    ttft: float | None = None
    out_chars = 0
    try:
        async for piece in llm.chat_stream(
            [LLMMessage(role="user", content=PROMPT)],
            system=SYSTEM,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
        ):
            if piece:
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                out_chars += len(piece)
        total_ms = (time.perf_counter() - t0) * 1000
        return RoundStats(ttft_ms=ttft, total_ms=total_ms, out_chars=out_chars)
    except Exception as exc:  # noqa: BLE001 — live probe
        return RoundStats(
            ttft_ms=None,
            total_ms=(time.perf_counter() - t0) * 1000,
            out_chars=out_chars,
            error=str(exc),
        )


async def chat_round(llm: MinimaxCNLLM) -> RoundStats:
    t0 = time.perf_counter()
    try:
        resp = await llm.chat(
            [LLMMessage(role="user", content=PROMPT)],
            system=SYSTEM,
            max_tokens=MAX_TOKENS,
            temperature=0.3,
        )
        total_ms = (time.perf_counter() - t0) * 1000
        text = (resp.content or "") + (resp.reasoning or "")
        return RoundStats(ttft_ms=None, total_ms=total_ms, out_chars=len(text))
    except Exception as exc:  # noqa: BLE001
        return RoundStats(
            ttft_ms=None,
            total_ms=(time.perf_counter() - t0) * 1000,
            out_chars=0,
            error=str(exc),
        )


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


async def bench_model(
    api_key: str,
    base_url: str,
    group_id: str | None,
    model: str,
    rounds: int,
) -> None:
    extra = {"group_id": group_id} if group_id else None
    llm = MinimaxCNLLM(
        LLMConfig(
            provider="minimax_cn",
            api_key=api_key,
            model=model,
            base_url=base_url,
            extra=extra,
        )
    )
    print(f"\n=== {model} ({rounds} rounds, max_tokens={MAX_TOKENS}) ===")

    stream_stats: list[RoundStats] = []
    for i in range(rounds):
        st = await stream_round(llm)
        stream_stats.append(st)
        if st.error:
            print(f"  stream {i + 1}: ERROR {st.error}")
        else:
            tps = (
                st.out_chars / (st.total_ms / 1000)
                if st.total_ms > 0 and st.out_chars
                else 0
            )
            print(
                f"  stream {i + 1}: TTFT={st.ttft_ms:.0f}ms "
                f"total={st.total_ms:.0f}ms chars={st.out_chars} "
                f"~{tps:.0f} chars/s"
            )

    chat_stats: list[RoundStats] = []
    for i in range(rounds):
        st = await chat_round(llm)
        chat_stats.append(st)
        if st.error:
            print(f"  chat   {i + 1}: ERROR {st.error}")
        else:
            print(
                f"  chat   {i + 1}: total={st.total_ms:.0f}ms chars={st.out_chars}"
            )

    ok_stream = [s for s in stream_stats if not s.error and s.ttft_ms is not None]
    ok_chat = [s for s in chat_stats if not s.error]
    if ok_stream:
        print(
            f"  stream avg: TTFT={_avg([s.ttft_ms for s in ok_stream]):.0f}ms "
            f"total={_avg([s.total_ms for s in ok_stream]):.0f}ms "
            f"chars={_avg([s.out_chars for s in ok_stream]):.0f}"
        )
    if ok_chat:
        print(
            f"  chat   avg: total={_avg([s.total_ms for s in ok_chat]):.0f}ms "
            f"chars={_avg([s.out_chars for s in ok_chat]):.0f}"
        )


async def resolve_credentials(cli_key: str | None) -> tuple[str, str, str | None]:
    api_key = (cli_key or os.getenv("OPENAI_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    group_id = (os.getenv("MINIMAX_GROUP_ID") or "").strip() or None

    if not api_key:
        merged = await get_merged_settings()
        api_key = str(merged.get("llm_api_key") or merged.get("planner_llm_api_key") or "").strip()
        if not base_url:
            base_url = str(
                merged.get("planner_llm_base_url")
                or merged.get("llm_base_url")
                or ""
            ).strip()
        if not group_id:
            gid = str(merged.get("llm_group_id") or merged.get("planner_llm_group_id") or "").strip()
            group_id = gid or None

    if not base_url:
        base_url = "https://api.minimaxi.com/v1"
    return api_key, base_url, group_id


async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark MiniMax model latency")
    parser.add_argument("--api-key", help="MiniMax API Key（也可用 OPENAI_API_KEY 环境变量）")
    parser.add_argument("--rounds", type=int, default=3, help="每个模型重复次数")
    args = parser.parse_args()

    api_key, base_url, group_id = await resolve_credentials(args.api_key)

    if not api_key:
        print("ERROR: 未找到 API Key。")
        print("  请在设置页保存 MiniMax Key，或执行：")
        print("  OPENAI_API_KEY=sk-... python scripts/benchmark_minimax_models.py")
        sys.exit(1)

    print("MiniMax 模型响应速度对比")
    print(f"base_url={base_url}")
    print(f"group_id={'(set)' if group_id else '(default)'}")
    print(f"prompt chars={len(PROMPT)}")

    for model in MODELS:
        await bench_model(api_key, base_url, group_id, model, args.rounds)

    print("\n说明：stream 指标含首 token 延迟(TTFT)；chat 为非流式整包延迟。")


if __name__ == "__main__":
    asyncio.run(main())
