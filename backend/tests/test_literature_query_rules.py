from app.agents.literature_query_rules import is_mom_ambiguous, is_mom_manufacturing_context


def test_mom_manufacturing_context() -> None:
    assert is_mom_manufacturing_context("AI-native MOM 制造运营")
    assert not is_mom_manufacturing_context("Mixture-of-Memories model")


def test_mom_ambiguous() -> None:
    assert is_mom_ambiguous("AI native MOM survey")
    assert not is_mom_ambiguous("AI-native MOM 制造运营")
