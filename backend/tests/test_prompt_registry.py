"""Tests for configurable prompt template registry."""
from __future__ import annotations

from app.agents.prompt_registry import (
    PROMPT_SPECS,
    clamp_prompt_params,
    default_for,
    resolve_prompt_template,
)


def test_understanding_default_is_domain_agnostic() -> None:
    tpl = default_for("understanding_system_template")
    assert "过程解说员" in tpl
    assert "search_aspects" in tpl
    assert "MOM" not in tpl


def test_expansion_and_refiner_roles_differ() -> None:
    # search_expansion removed in v2 (扩展并入子主题识别)
    refiner = default_for("search_refiner_system_template")
    assert "1:1" in refiner or "1:1 精炼" in refiner
    assert "exclude_title_substrings" in refiner


def test_matrix_and_query_defaults_share_material_labels() -> None:
    matrix = default_for("matrix_system_template")
    query = default_for("query_corpus_system_template")
    section = default_for("section_system_template")
    for tpl in (matrix, query, section):
        assert "[网页材料]" in tpl
    assert "[web_search]" in matrix
    assert "【多源材料】" in query
    assert "【挂载文献】" in section


def test_resolve_uses_builtin_when_override_empty() -> None:
    out = resolve_prompt_template("intent_router_system_template", "")
    assert "intent" in out
    assert default_for("intent_router_system_template") == out


def test_resolve_appends_contract_when_custom_omits_marker() -> None:
    custom = "你是意图路由器，请根据用户问题输出 JSON。"
    out = resolve_prompt_template("intent_router_system_template", custom)
    assert custom in out
    assert "intent" in out


def test_resolve_keeps_custom_when_contract_present() -> None:
    custom = default_for("assessor_system_template")
    out = resolve_prompt_template("assessor_system_template", custom)
    assert out == custom


def test_prompt_metadata_includes_max_tokens() -> None:
    from app.agents.prompt_registry import prompt_registry_metadata

    meta = prompt_registry_metadata()
    understanding = next(m for m in meta if m["key"] == "understanding_system_template")
    assert understanding["default_max_tokens"] == 1200
    assert understanding["max_tokens_limit"] == 4000


def test_clamp_prompt_params_truncates_long_templates() -> None:
    key = "summary_system_template"
    max_len = int(PROMPT_SPECS[key]["max_len"])
    long_val = "x" * (max_len + 50)
    out = clamp_prompt_params({key: long_val, "outline_mode": "lite"})
    assert len(out[key]) == max_len
    assert out["outline_mode"] == "lite"
