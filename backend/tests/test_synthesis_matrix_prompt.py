from app.agents.synthesis_matrix_prompt import (
    SYNTHESIS_MATRIX_LANG,
    build_synthesis_matrix_system_prompt,
    build_synthesis_matrix_user_prompt,
)


def test_matrix_system_prompt_includes_directives() -> None:
    out = build_synthesis_matrix_system_prompt(
        initial_query="AI-Native MOM",
        gen_directives="突出架构演进",
    )

    assert "Synthesis Matrix" in out
    assert "AI-Native MOM" in out
    assert "架构演进" in out
    assert "[网页材料]" in out
    assert "工业软件" not in out


def test_matrix_user_prompt_wraps_materials() -> None:
    out = build_synthesis_matrix_user_prompt("## [网页材料] Paper\nbody")

    assert "【多源材料】" in out
    assert "[网页材料]" in out
    assert "web_fetch" not in out
    assert "## [网页材料] Paper" in out


def test_matrix_artifact_lang() -> None:
    assert SYNTHESIS_MATRIX_LANG == "literature-matrix+markdown"
