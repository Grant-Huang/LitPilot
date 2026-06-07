from app.agents.workflow_graph import (
    apply_fetch_provider_label,
    build_literature_graph,
    fetch_node_description,
)


def test_v2_graph_understand_search_filter_fetch() -> None:
    g = build_literature_graph()
    ids = [n.id for n in g.nodes]
    assert ids[0] == "understand"
    assert "search" in ids
    assert "filter" in ids
    assert "fetch" in ids
    assert "matrix" in ids
    assert "deliver" in ids
    assert "attributes" not in ids
    assert "refine" not in ids
    assert "generate" not in ids


def test_v2_graph_grows_with_sections() -> None:
    specs = [("sec-a", "章节 A"), ("sec-b", "章节 B")]
    g = build_literature_graph(specs)
    ids = [n.id for n in g.nodes]
    assert "sec-a" in ids
    assert "sec-b" in ids
    assert ids.index("sec-a") < ids.index("sec-b")
    assert ids.index("sec-b") < ids.index("matrix")
    assert ids.index("matrix") < ids.index("deliver")


def test_fetch_node_description_reflects_provider() -> None:
    assert "native" in fetch_node_description("native")
    assert "Jina Reader" in fetch_node_description("jina")
    g = build_literature_graph()
    apply_fetch_provider_label(g, "native")
    assert g.node("fetch").description == fetch_node_description("native")
