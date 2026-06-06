#!/usr/bin/env python3
"""Live smoke: multi_academic search for AI-native MOM four-aspect brief."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.research_decompose import decompose_research_brief
from app.agents.tools.providers import multi_academic as ma

USER_BRIEF = (
    "我要写一个与AI原生MOM有关的文献综述，包括4个方面："
    "其一，AI原生MOM系统性的定义框架与参考模型。"
    "其二，异构机器间信任建立的工程方案与制造知识图谱。"
    "其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，"
    "及其统一的工程整合框架。"
    "其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"
)

FALLBACK_QUERIES = [
    '"AI-native" manufacturing operations management',
    '"industrial knowledge graph" manufacturing ontology heterogeneous',
    '"multi-agent" manufacturing "large language model" framework',
    '"manufacturing execution system" migration microservices modernization',
]


async def main() -> int:
    topics = decompose_research_brief(USER_BRIEF)
    if len(topics) >= 4:
        # Academic APIs (arXiv/CrossRef/SS) need English queries; labels stay Chinese.
        pairs = [
            (t.title, eng_q)
            for t, eng_q in zip(topics[:4], FALLBACK_QUERIES, strict=True)
        ]
    else:
        labels = [
            "方向一：定义框架与参考模型",
            "方向二：信任与知识图谱",
            "方向三：多智能体与微服务整合",
            "方向四：渐进式迁移",
        ]
        pairs = list(zip(labels, FALLBACK_QUERIES, strict=True))

    print("=== multi_academic · AI-native MOM 四方向检索 ===\n")
    total = 0
    for label, query in pairs:
        print(f"## {label}")
        print(f"   query: {query}")
        out = await ma.search(query, max_results=8)
        hits = out.get("results") or []
        counts = out.get("source_counts") or {}
        total += len(hits)
        print(f"   merged: {len(hits)} | per-source: {counts}\n")
        for i, h in enumerate(hits[:5], 1):
            src = h.get("source", "?")
            title = (h.get("title") or "")[:72]
            url = h.get("url") or ""
            print(f"   [{i}] [{src}] {title}")
            print(f"       {url}")
        if not hits:
            print("   (无命中)")
        print()

    print(f"合计 {total} 条候选 URL（四方向）")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
