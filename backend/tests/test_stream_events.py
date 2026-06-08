from app.core.stream_events import (
    literature_brief_assessment,
    literature_phase_think,
    process_text_extension,
)


def test_literature_phase_think_extension() -> None:
    ev = literature_phase_think("understand", "解说正文")
    assert ev[0] == "extension"
    assert ev[1]["name"] == "literature_phase_think"
    assert ev[1]["data"]["stage"] == "understand"
    assert ev[1]["data"]["content"] == "解说正文"


def test_literature_brief_assessment_extension() -> None:
    payload = {"core_research_questions": ["RQ1"], "keywords": ["kw"]}
    ev = literature_brief_assessment(payload)
    assert ev[0] == "extension"
    assert ev[1]["name"] == "literature_brief_assessment"
    assert ev[1]["data"] == payload


def test_process_text_extension() -> None:
    ev = process_text_extension("RQ 摘要\n\n")
    assert ev[0] == "extension"
    assert ev[1]["name"] == "process_text"
    assert ev[1]["data"]["delta"] == "RQ 摘要\n\n"
