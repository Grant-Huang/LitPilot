export type NodeStatus =
  | "pending"
  | "active"
  | "done"
  | "skipped"
  | "error";

export type WorkflowGraphJson = {
  version: string;
  id: string;
  title: string;
  nodes: {
    id: string;
    label: string;
    kind: string;
    status: NodeStatus;
    description?: string;
  }[];
  edges: { id: string; source: string; target: string; label?: string }[];
};

export const WORKFLOW_GRAPH_LANG = "workflow-graph";

export function parseWorkflowGraph(content: string): WorkflowGraphJson | null {
  const trimmed = (content || "").trim();
  if (!trimmed) return null;
  try {
    const data = JSON.parse(trimmed) as WorkflowGraphJson;
    if (!Array.isArray(data.nodes) || !Array.isArray(data.edges)) return null;
    return data;
  } catch {
    const start = trimmed.lastIndexOf("{");
    if (start < 0) return null;
    try {
      return JSON.parse(trimmed.slice(start)) as WorkflowGraphJson;
    } catch {
      return null;
    }
  }
}

export function findWorkflowArtifact(
  artifacts: Record<string, { lang: string; content: string; done: boolean }>,
  order: string[],
): { id: string; graph: WorkflowGraphJson } | null {
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const id = order[i];
    const art = artifacts[id];
    if (!art || art.lang !== WORKFLOW_GRAPH_LANG) continue;
    const graph = parseWorkflowGraph(art.content);
    if (graph) return { id, graph };
  }
  return null;
}
