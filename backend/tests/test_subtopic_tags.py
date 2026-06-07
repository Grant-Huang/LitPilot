from app.library.subtopic_tags import merge_subtopic_tags, parse_subtopic_ids, subtopic_tag


def test_subtopic_tag_prefix() -> None:
    assert subtopic_tag("Trust Arch") == "st:trust_arch"


def test_parse_subtopic_ids() -> None:
    assert parse_subtopic_ids(["st:a", "other", "st:b"]) == ["a", "b"]


def test_merge_subtopic_tags() -> None:
    merged = merge_subtopic_tags(["st:a"], ["b", "a"])
    assert merged == ["st:a", "st:b"]
