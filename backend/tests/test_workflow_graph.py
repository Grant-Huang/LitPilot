from app.agents.workflow_graph import (
    apply_fetch_provider_label,
    build_literature_graph,
    build_literature_graph_legacy,
    fetch_node_description,
)


def test_legacy_graph_four_nodes() -> None:
    g = build_literature_graph_legacy()
    assert len(g.nodes) == 4
    ids = {n.id for n in g.nodes}
    assert ids == {"fetch", "cite_extract", "generate", "deliver"}


def test_dynamic_graph_grows_with_sections() -> None:
    specs = [("sec-a", "章节 A"), ("sec-b", "章节 B")]
    g = build_literature_graph(specs)
    ids = [n.id for n in g.nodes]
    assert "attributes" in ids
    assert "outline" in ids
    assert "refine" in ids
    assert "sec-a" in ids
    assert "sec-b" in ids
    assert ids.index("sec-a") < ids.index("sec-b")
    assert ids.index("sec-b") < ids.index("refine")


def test_fetch_node_description_reflects_provider() -> None:
    assert "native" in fetch_node_description("native")
    assert "Jina Reader" in fetch_node_description("jina")
    g = build_literature_graph_legacy()
    apply_fetch_provider_label(g, "native")
    assert g.node("fetch").description == fetch_node_description("native")
