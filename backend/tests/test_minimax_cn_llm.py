from app.llm.minimax_cn_llm import MinimaxCNLLM


def test_split_think_strips_complete_block() -> None:
    raw = (
        "<think>internal</think>\n\n"
        "# Public review\n\nBody text."
    )
    reasoning, visible = MinimaxCNLLM._split_think(raw)
    assert "internal" in reasoning
    assert "Public review" in visible
    assert "redacted_thinking" not in visible


def test_split_think_all_inside_block_yields_empty_visible() -> None:
    raw = "<think>\n\n# Only inside think\n\n</think>"
    reasoning, visible = MinimaxCNLLM._split_think(raw)
    assert "Only inside think" in reasoning
    assert not visible.strip()
