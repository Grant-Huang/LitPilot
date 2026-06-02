from app.agents.literature_post_refine import post_refine_review
from app.agents.literature_outline import prepare_outline


def test_post_refine_removes_boilerplate() -> None:
    text = "## 一、背景\n\n内容段落。\n\n综上所述，本文已完成综述。\n"
    refined, report = post_refine_review(text)
    assert "综上所述" not in refined
    assert report["removed_boilerplate"] >= 1


def test_post_refine_detects_missing_sections() -> None:
    outline = prepare_outline(
        user_message=(
            "其一，AI原生MOM系统性的定义框架与参考模型。\n"
            "其二，异构机器间信任建立的工程方案与制造知识图谱。"
        ),
        search_query="test",
    )
    text = "# 导言\n\n仅导言内容。"
    _, report = post_refine_review(text, outline=outline)
    assert report["missing_sections"]
