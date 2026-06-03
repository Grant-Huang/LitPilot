import pytest

from app.agents.llm_json import parse_json_object


def test_parse_json_object_from_markdown_wrapped() -> None:
    data = parse_json_object('说明\n{"session_title":"t","search_query":"q"}\n')
    assert data["session_title"] == "t"


def test_parse_json_object_raises_when_missing() -> None:
    with pytest.raises(ValueError):
        parse_json_object("no json here")
