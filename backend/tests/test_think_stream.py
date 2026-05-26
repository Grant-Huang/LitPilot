from app.core.think_stream import ThinkAccumulator, emit_think_events


async def _collect_think_events(text: str, acc: ThinkAccumulator) -> list[str]:
    deltas: list[str] = []
    async for kind, payload in emit_think_events(text, accumulator=acc):
        assert kind == "think"
        delta = payload.get("delta")
        if delta:
            deltas.append(str(delta))
    return deltas


def test_think_accumulator_joins_blocks() -> None:
    acc = ThinkAccumulator()
    acc.append("研究主题：AI MOM")
    acc.append("✓ 文献检索（3 条命中）")
    assert acc.finalize() == "研究主题：AI MOM\n\n✓ 文献检索（3 条命中）"


async def test_emit_think_events_records_accumulator() -> None:
    acc = ThinkAccumulator()
    deltas = await _collect_think_events("并行抓取 2 篇来源…", acc)
    assert "".join(deltas) == "并行抓取 2 篇来源…"
    assert acc.finalize() == "并行抓取 2 篇来源…"
