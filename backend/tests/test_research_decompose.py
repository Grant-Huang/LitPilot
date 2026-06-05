from app.agents.research_decompose import decompose_research_brief, is_polluted_search_query


MOM_BRIEF = """我要写一个与AI原生MOM有关的文献综述，包括4个方面：
其一，AI原生MOM系统性的定义框架与参考模型。
其二，异构机器间信任建立的工程方案与制造知识图谱。
其三，多智能体协作、动态知识推理与可组合微服务架构三条研究线索，及其统一的工程整合框架。
其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"""


def test_decompose_mom_four_aspects() -> None:
    topics = decompose_research_brief(MOM_BRIEF, base_query="AI-native MOM")
    assert len(topics) == 4
    assert "定义框架" in topics[0].title or "定义框架" in topics[0].description
    assert "信任" in topics[1].description
    assert "多智能体" in topics[2].description
    assert "迁移" in topics[3].description
    assert all(t.search_query for t in topics)
    assert not is_polluted_search_query(topics[0].search_query)
    assert topics[0].search_query != topics[1].search_query
    assert "我要写" not in topics[0].search_query


def test_decompose_ignores_polluted_base_query() -> None:
    polluted = MOM_BRIEF[:200]
    topics = decompose_research_brief(MOM_BRIEF, base_query=polluted)
    assert len(topics) == 4
    assert all(not is_polluted_search_query(t.search_query) for t in topics)
    assert all("其一" not in t.search_query for t in topics)


def test_decompose_inline_aspect_same_line() -> None:
    inline = (
        "我要写一个与AI原生MOM有关的文献综述，包括4个方面："
        "其一，AI原生MOM系统性的定义框架与参考模型。"
        "其二，异构机器间信任建立的工程方案与制造知识图谱。"
        "其三，多智能体协作、动态知识推理与可组合微服务架构。"
        "其四，从传统单体MOM向AI原生MOM的渐进式迁移的工程框架。"
    )
    topics = decompose_research_brief(inline, base_query="AI-native MOM")
    assert len(topics) == 4


def test_decompose_single_aspect_returns_empty() -> None:
    topics = decompose_research_brief(
        "请综述 transformer 在 NLP 中的应用",
        base_query="transformer NLP",
    )
    assert topics == []
