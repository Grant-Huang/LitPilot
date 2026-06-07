from app.agents.literature_outline import (
    build_subtopic_plan,
    mount_papers_by_subtopic_tags,
)
from app.schemas.corpus_paper import CorpusPaperRecord


def test_build_subtopic_plan_from_multi_aspect_brief() -> None:
    brief = """其一，AI原生MOM系统性的定义框架与参考模型综述。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构研究线索。"""
    outline, sub_topics = build_subtopic_plan(
        user_message=brief,
        search_query="AI MOM",
        session_title="AI MOM 综述",
        intent="new_topic",
    )
    body = [s for s in outline.sections if s.sub_topic_id]
    assert len(body) == 3
    assert len(sub_topics) == 3
    assert outline.research_questions


def test_mount_papers_by_subtopic_tags() -> None:
    brief = (
        "其一，异构机器间信任建立的工程方案与制造知识图谱。\n"
        "其二，多智能体协作与可组合微服务架构的工程整合框架。"
    )
    outline, sub_topics = build_subtopic_plan(
        user_message=brief,
        search_query="MOM",
        intent="new_topic",
    )
    st1 = sub_topics[0].id
    st2 = sub_topics[1].id
    papers = [
        CorpusPaperRecord(
            url="https://a.com/1",
            title="制造知识图谱与信任机制",
            subtopic_tags=[st1],
            cite_in_review=True,
        ).to_dict(),
        CorpusPaperRecord(
            url="https://a.com/2",
            title="微服务架构综述",
            subtopic_tags=[st2],
            cite_in_review=True,
        ).to_dict(),
    ]
    mounted = mount_papers_by_subtopic_tags(outline, papers)
    body = [s for s in mounted.sections if s.sub_topic_id]
    assert any("https://a.com/1" in s.mounted_paper_ids for s in body)
    assert any("https://a.com/2" in s.mounted_paper_ids for s in body)


def test_review_refine_reuses_stored_outline() -> None:
    brief = """其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。"""
    outline, sub_topics = build_subtopic_plan(
        user_message=brief,
        search_query="AI-native MOM",
        session_title="AI MOM",
        intent="new_topic",
    )
    reused, reused_subs = build_subtopic_plan(
        user_message="只改第二章",
        search_query="AI-native MOM",
        session_title="AI MOM",
        stored_outline=outline,
        intent="review_refine",
    )
    assert reused is outline
    assert len(reused_subs) == len(sub_topics)
