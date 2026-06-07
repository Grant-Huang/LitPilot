"""Tests for review prompt rendering."""
from app.agents.review_prompt import (
    MAX_REVIEW_SYSTEM_PROMPT_LEN,
    build_review_materials_user_prompt,
    build_review_system_prompt,
    build_review_turn_system_prompt,
    default_review_system_prompt_template,
    material_sections_guide,
)


def test_default_prompt_apa() -> None:
    out = build_review_system_prompt("apa", None)
    assert "APA" in out
    assert "学术文献综述助手" in out
    assert "[web_search]" in out
    assert "[Tavily]" not in out
    assert "材料分栏说明" in out


def test_default_prompt_acm() -> None:
    out = build_review_system_prompt("acm", "")
    assert "ACM" in out


def test_custom_template_variables() -> None:
    tpl = "格式 {fmt_label}，代码 {citation_format}。"
    out = build_review_system_prompt("apa", tpl)
    assert out == "格式 APA，代码 apa。"


def test_invalid_template_falls_back() -> None:
    tpl = "broken {unknown_var}"
    out = build_review_system_prompt("apa", tpl)
    assert "学术文献综述助手" in out
    assert "APA" in out


def test_default_template_has_placeholders() -> None:
    raw = default_review_system_prompt_template()
    assert "{fmt_label}" in raw


def test_max_length_constant() -> None:
    assert MAX_REVIEW_SYSTEM_PROMPT_LEN >= 4000


def test_materials_user_prompt_has_no_user_question() -> None:
    out = build_review_materials_user_prompt("## block")
    assert "【多源材料】" in out
    assert "用户研究问题" not in out


def test_material_sections_guide_shared_labels() -> None:
    guide = material_sections_guide("APA")
    assert "[web_search]" in guide
    assert "[网页材料]" in guide
    assert "APA" in guide
    assert "[Tavily]" not in guide


def test_turn_system_prompt_holds_constraints() -> None:
    out = build_review_turn_system_prompt(
        "apa",
        None,
        initial_query="LLM hallucination survey",
        gen_constraints=["增加伦理一节"],
        intent="review_refine",
    )
    assert "伦理" in out
    assert "不得复述" in out
    assert "LLM hallucination" in out
