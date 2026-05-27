from app.agents.tools.jina_reader import normalize_reader_target_url


def test_normalize_reader_target_adds_scheme() -> None:
    assert (
        normalize_reader_target_url("example.com/paper")
        == "https://example.com/paper"
    )


def test_normalize_reader_target_prefers_arxiv_pdf() -> None:
    assert (
        normalize_reader_target_url("https://arxiv.org/abs/2401.00001v2")
        == "https://arxiv.org/pdf/2401.00001v2.pdf"
    )


def test_normalize_reader_target_keeps_existing_pdf() -> None:
    url = "https://arxiv.org/pdf/2401.00001.pdf"
    assert normalize_reader_target_url(url) == url


def test_normalize_reader_target_keeps_non_arxiv_url() -> None:
    url = "https://openreview.net/forum?id=abc"
    assert normalize_reader_target_url(url) == url
