import type { WorkflowNodeState, WorkflowRunState } from "@meso/types";
import type { NodeStatus, WorkflowGraphJson } from "@/lib/workflowGraph";

export function workflowNodeStateToGraphStatus(
  state: WorkflowNodeState,
): NodeStatus {
  switch (state) {
    case "active":
      return "active";
    case "done":
      return "done";
    case "error":
      return "error";
    case "skipped":
      return "skipped";
    default:
      return "pending";
  }
}

const ROLLUP_PRIORITY: NodeStatus[] = ["error", "active", "done", "skipped"];

function rollupStatuses(statuses: NodeStatus[]): NodeStatus | null {
  if (statuses.length === 0) return null;
  for (const s of ROLLUP_PRIORITY) {
    if (statuses.includes(s)) return s;
  }
  return "pending";
}

function cloneGraph(graph: WorkflowGraphJson): WorkflowGraphJson {
  return {
    ...graph,
    nodes: graph.nodes.map((n) => ({ ...n })),
    edges: graph.edges.map((e) => ({ ...e })),
  };
}

function resolveGraphNodeStatus(
  run: WorkflowRunState,
  graphNodeId: string,
): NodeStatus | null {
  const direct = run.nodes[graphNodeId];
  if (direct) return workflowNodeStateToGraphStatus(direct.state);

  const childStatuses = run.nodeOrder
    .map((id) => run.nodes[id])
    .filter((n) => n?.parent_id === graphNodeId)
    .map((n) => workflowNodeStateToGraphStatus(n!.state));

  return rollupStatuses(childStatuses);
}

/** Overlay live workflow_node SSE onto a workflow-graph artifact snapshot. */
export function mergeWorkflowRunsIntoGraph(
  graph: WorkflowGraphJson,
  artifactId: string,
  runs: WorkflowRunState[],
): WorkflowGraphJson {
  if (!runs.length) return graph;

  const run =
    runs.find((r) => r.run_id === artifactId) ?? runs[runs.length - 1];
  if (!run?.nodeOrder.length) return graph;

  const merged = cloneGraph(graph);
  for (const node of merged.nodes) {
    const live = resolveGraphNodeStatus(run, node.id);
    if (live) node.status = live;
  }
  return merged;
}
