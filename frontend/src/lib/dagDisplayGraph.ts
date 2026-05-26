import type { WorkflowGraphJson } from "@/lib/workflowGraph";

/** DAG 侧栏仅展示抓取及之后阶段；检索/路由在主页思考区展示。 */
const DAG_NODE_IDS = new Set([
  "fetch",
  "cite_extract",
  "generate",
  "deliver",
]);

export function graphForDagDisplay(graph: WorkflowGraphJson): WorkflowGraphJson {
  const nodes = graph.nodes.filter((n) => DAG_NODE_IDS.has(n.id));
  const ids = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter(
    (e) => ids.has(e.source) && ids.has(e.target),
  );
  const hasFetchToCite = edges.some(
    (e) => e.source === "fetch" && e.target === "cite_extract",
  );
  const extraEdges = hasFetchToCite
    ? []
    : [
        {
          id: "dag-fetch-cite",
          source: "fetch",
          target: "cite_extract",
          label: "",
        },
      ];
  return {
    ...graph,
    title: graph.title || "文献处理流水线",
    nodes,
    edges: [...edges, ...extraEdges],
  };
}
