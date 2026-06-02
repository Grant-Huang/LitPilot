"""MOM 四 aspect 检索容量分析（无需网络）。"""
from __future__ import annotations

from app.agents.agent_settings import TAVILY_MAX_RESULTS_CAP
from app.agents.research_decompose import decompose_research_brief
from app.agents.search_merge import merge_search_hits
from app.agents.tools.tavily_search import augment_literature_search_query

MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，及其统一的工程整合框架。
其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"""


def test_mom_decompose_four_subtopics() -> None:
    topics = decompose_research_brief(MOM_BRIEF, base_query="AI-native MOM")
    assert len(topics) == 4


def test_mom_subtopic_search_merge_cap() -> None:
    """M2 分 4 轮检索时，合并后命中上限 = min(tavily_max_results, 去重后总数)。"""
    topics = decompose_research_brief(MOM_BRIEF, base_query="AI-native MOM")
    tavily_max = 80
    per_query = max(2, tavily_max // len(topics))
    assert per_query == 20

    fake_lists = [
        [{"url": f"https://example.com/{i}-{j}", "title": f"T{i}-{j}"} for j in range(per_query)]
        for i in range(len(topics))
    ]
    merged = merge_search_hits(fake_lists, max_results=tavily_max)
    assert len(merged) == tavily_max

    queries = [augment_literature_search_query(t.search_query) for t in topics]
    assert all("site:" in q or "academic" in q.lower() or "survey" in q.lower() for q in queries)


def test_tavily_hard_cap_is_80() -> None:
    assert TAVILY_MAX_RESULTS_CAP == 80
