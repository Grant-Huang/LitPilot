from app.agents.tavily_key import looks_like_tavily_api_key, tavily_key_hint


def test_looks_like_tavily() -> None:
    assert looks_like_tavily_api_key("tvly-dev-abc")
    assert not looks_like_tavily_api_key("sk-abc")


def test_hint_for_sk_prefix() -> None:
    assert "sk-" in tavily_key_hint("sk-cp-test")
    assert "tvly-" in tavily_key_hint("sk-cp-test")
