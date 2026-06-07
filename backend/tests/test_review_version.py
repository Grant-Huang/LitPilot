from app.agents.review_version import (
    next_full_review_version_id,
    next_refine_review_version_id,
    resolve_review_version_id,
)


def test_next_full_version_empty() -> None:
    assert next_full_review_version_id(None) == "v1"


def test_next_full_version_increment() -> None:
    meta = {"review_versions": [{"id": "v3"}, {"id": "v3a"}]}
    assert next_full_review_version_id(meta) == "v4"


def test_next_refine_from_full() -> None:
    meta = {"review_versions": [{"id": "v2"}]}
    assert next_refine_review_version_id(meta) == "v2a"


def test_next_refine_suffix_chain() -> None:
    meta = {"review_versions": [{"id": "v2"}, {"id": "v2a"}]}
    assert next_refine_review_version_id(meta) == "v2b"


def test_resolve_review_refine() -> None:
    meta = {"review_versions": [{"id": "v1"}]}
    assert resolve_review_version_id(meta=meta, intent="review_refine") == "v1a"


def test_resolve_full_regen() -> None:
    meta = {"review_versions": [{"id": "v1a"}]}
    assert resolve_review_version_id(
        meta=meta,
        intent="review_refine",
        full_regen=True,
    ) == "v2"
