#!/usr/bin/env python3
"""Live probe: Semantic Scholar search with rate-limit pacing (no key vs with key)."""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.tools.providers.academic import semantic_scholar as ss
from app.agents.tools.providers.academic import ss_rate_limit


QUERY = "multi-agent manufacturing large language model"


async def probe(label: str, api_key: str, rounds: int = 3) -> None:
    ss_rate_limit.reset_for_tests()
    print(f"\n=== {label} ({rounds} queries) ===")
    t0 = time.monotonic()
    ok = 0
    empty = 0
    for i in range(rounds):
        t1 = time.monotonic()
        rows = await ss.search(QUERY, limit=5, min_year=2019, api_key=api_key)
        dt = time.monotonic() - t1
        n = len(rows)
        if n:
            ok += 1
        else:
            empty += 1
        print(f"  round {i + 1}: hits={n} elapsed={dt:.1f}s")
    total = time.monotonic() - t0
    print(f"  summary: ok={ok} empty={empty} total={total:.1f}s avg={total / rounds:.1f}s/query")


async def main() -> None:
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    print("SS rate-limit live probe")
    print(f"  BASE no-key={ss_rate_limit.BASE_INTERVAL_NO_KEY}s")
    print(f"  BASE with-key={ss_rate_limit.BASE_INTERVAL_WITH_KEY}s")
    print(f"  429 backoff: {ss_rate_limit.BACKOFF_INITIAL_SEC}s initial, cap {ss_rate_limit.BACKOFF_MAX_SEC}s")
    await probe("anonymous (no key)", "", rounds=3)
    if key:
        await probe("with API key", key, rounds=3)
    else:
        print("\n(skip with-key probe: set SEMANTIC_SCHOLAR_API_KEY)")


if __name__ == "__main__":
    asyncio.run(main())
