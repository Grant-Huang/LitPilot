from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

NodeStatus = Literal["pending", "active", "done", "skipped", "error"]
NodeKind = Literal[
    "router",
    "search",
    "fetch",
    "cite_extract",
    "llm",
    "deliver",
    "chat",
]


@dataclass
class WorkflowNode:
    id: str
    label: str
    kind: NodeKind
    status: NodeStatus = "pending"
    description: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowEdge:
    id: str
    source: str
    target: str
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowGraph:
    id: str
    title: str
    version: str = "1.0"
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "title": self.title,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def node(self, node_id: str) -> WorkflowNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def set_node_status(self, node_id: str, status: NodeStatus) -> None:
        n = self.node(node_id)
        if n:
            n.status = status

    def clone(self) -> WorkflowGraph:
        return deepcopy(self)


def build_literature_graph() -> WorkflowGraph:
    """Artifact DAG：仅抓取及之后阶段（检索/路由在思考区展示）。"""
    nodes = [
        WorkflowNode("fetch", "抓取全文", "fetch", description="Jina Reader / web_fetch"),
        WorkflowNode("cite_extract", "引用抽取", "cite_extract", description="引用元数据"),
        WorkflowNode("generate", "综述生成", "llm", description="LLM 综合写作"),
        WorkflowNode("deliver", "交付", "deliver", description="保存引用与 Artifact"),
    ]
    edges = [
        WorkflowEdge("e1", "fetch", "cite_extract"),
        WorkflowEdge("e2", "cite_extract", "generate"),
        WorkflowEdge("e3", "generate", "deliver"),
    ]
    return WorkflowGraph(
        id="literature-agent",
        title="文献综述执行计划",
        nodes=nodes,
        edges=edges,
    )
