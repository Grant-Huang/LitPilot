import type { StreamState } from "@meso/ui";
import { WORKFLOW_GRAPH_LANG } from "@/lib/workflowGraph";

/** Hide workflow-graph from inline chat; show in right Artifact column. */
export function stripWorkflowArtifacts(state: StreamState): StreamState {
  const artifactOrder = state.artifactOrder.filter(
    (id) => state.artifacts[id]?.lang !== WORKFLOW_GRAPH_LANG,
  );
  const artifacts = Object.fromEntries(
    artifactOrder.map((id) => [id, state.artifacts[id]]),
  );
  return { ...state, artifactOrder, artifacts };
}
