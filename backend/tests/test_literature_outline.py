from app.agents.literature_outline import mount_papers_to_outline, prepare_outline, resolve_outline_plan
from app.schemas.paper_record import PaperRecord


def test_prepare_outline_from_multi_aspect_brief() -> None:
    brief = """其一，AI原生MOM系统性的定义框架与参考模型综述。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构研究线索。"""
    outline = prepare_outline(
        user_message=brief,
        search_query="AI MOM",
        session_title="AI MOM 综述",
    )
    body = [s for s in outline.sections if s.id not in ("sec-intro", "sec-conclusion")]
    assert len(body) == 3
    assert outline.research_questions


def test_mount_papers_to_sections() -> None:
    outline = prepare_outline(
        user_message=(
            "其一，异构机器间信任建立的工程方案与制造知识图谱。\n"
            "其二，多智能体协作与可组合微服务架构的工程整合框架。"
        ),
        search_query="MOM",
    )
    papers = [
        PaperRecord(
            paper_id="p1",
            url="https://a.com/1",
            title="制造知识图谱与信任机制",
            attri={"problem": "异构机器信任", "keywords": ["知识图谱", "MOM"]},
        ).to_dict(),
        PaperRecord(
            paper_id="p2",
            url="https://a.com/2",
            title="微服务架构综述",
            attri={"method": "可组合微服务", "keywords": ["微服务", "架构"]},
        ).to_dict(),
    ]
    mounted = mount_papers_to_outline(outline, papers)
    body = [s for s in mounted.sections if s.sub_topic_id]
    assert any("p1" in s.mounted_paper_ids for s in body)
    assert mounted.status == "confirmed"


def test_resolve_outline_plan_single_decompose() -> None:
    brief = """其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。"""
    use, outline, sub_topics = resolve_outline_plan(
        outline_mode="lite",
        intent="new_topic",
        user_message=brief,
        initial_query=brief,
        search_query="AI-native MOM",
        session_title="AI MOM",
        stored_outline=None,
    )
    assert use is True
    assert outline is not None
    assert len(sub_topics) == 2
    assert len(outline.sub_topics) == 2
