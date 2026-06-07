from app.agents.session_corpus import SessionCorpus
from app.schemas.corpus_paper import (
    CorpusPaperRecord,
    FETCH_STATUS_FAILED,
    merge_corpus_papers,
)


def test_corpus_paper_roundtrip() -> None:
    rec = CorpusPaperRecord(
        url="https://example.com/a",
        title="A",
        subtopic_tags=["st1"],
        fetch_status=FETCH_STATUS_FAILED,
        cite_in_review=False,
    )
    restored = CorpusPaperRecord.from_dict(rec.to_dict())
    assert restored.url == rec.url
    assert restored.subtopic_tags == ["st1"]
    assert restored.cite_in_review is False


def test_merge_corpus_papers_tags() -> None:
    existing = [
        CorpusPaperRecord(url="https://a", subtopic_tags=["st1"]).to_dict(),
    ]
    incoming = [
        CorpusPaperRecord(url="https://a", subtopic_tags=["st2"]),
    ]
    merged = merge_corpus_papers(existing, incoming)
    assert merged[0]["subtopic_tags"] == ["st1", "st2"]


def test_session_corpus_v3_papers() -> None:
    c = SessionCorpus()
    c.merge_papers(
        [CorpusPaperRecord(url="https://x", title="X", subtopic_tags=["t1"])]
    )
    data = c.to_dict()
    assert data["version"] == 3
    assert data["papers"][0]["subtopic_tags"] == ["t1"]
