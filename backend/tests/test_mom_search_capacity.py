"""MOM 四 aspect 检索容量分析（无需网络）。"""
from __future__ import annotations

from app.agents.agent_settings import SEARCH_MAX_RESULTS_CAP
from app.agents.research_decompose import decompose_research_brief
from app.agents.search_merge import merge_search_hits
from app.agents.search_query_refiner import apply_academic_search_suffix

MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，及其统一的工程整合框架。
其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"""


def test_mom_decompose_four_subtopics() -> None:
    topics = decompose_research_brief(MOM_BRIEF, base_query="AI-native MOM")
    assert len(topics) == 4


def test_mom_subtopic_search_merge_accumulates() -> None:
    """M2 分 4 轮检索：每轮单源受 search_max 约束；跨 pass 合并按实际累计去重，不再截断。"""
    topics = decompose_research_brief(MOM_BRIEF, base_query="AI-native MOM")
    hits_per_pass = 20

    fake_lists = [
        [{"url": f"https://example.com/{i}-{j}", "title": f"T{i}-{j}"} for j in range(hits_per_pass)]
        for i in range(len(topics))
    ]
    merged = merge_search_hits(fake_lists)
    assert len(merged) == hits_per_pass * len(topics)

    queries = [apply_academic_search_suffix(t.search_query) for t in topics]
    assert all("site:" in q or "academic" in q.lower() or "survey" in q.lower() for q in queries)


def test_search_hard_cap_is_80() -> None:
    assert SEARCH_MAX_RESULTS_CAP == 80
