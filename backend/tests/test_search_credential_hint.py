from app.agents.search_credential_hint import (
    looks_like_tavily_secret,
    search_credential_secret_hint,
)


def test_looks_like_tavily_secret() -> None:
    assert looks_like_tavily_secret("tvly-dev-abc")
    assert not looks_like_tavily_secret("sk-abc")


def test_tavily_hint_for_wrong_prefix() -> None:
    assert "sk-" in search_credential_secret_hint("tavily", "sk-cp-test")
    assert "tvly-" in search_credential_secret_hint("tavily", "sk-cp-test")


def test_other_credential_types_no_hint() -> None:
    assert search_credential_secret_hint("brave", "sk-abc") == ""
