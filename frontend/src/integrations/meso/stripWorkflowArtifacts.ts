import type { StreamState } from "@meso.ai/ui";
import { WORKFLOW_GRAPH_LANG } from "@/lib/workflowGraph";
import { LITERATURE_OUTLINE_LANG } from "@/lib/literatureOutline";

const HIDDEN_INLINE_LANGS = new Set([WORKFLOW_GRAPH_LANG, LITERATURE_OUTLINE_LANG]);

/** Hide workflow-graph / outline JSON from inline chat; show in right Artifact column. */
export function stripWorkflowArtifacts(state: StreamState): StreamState {
  const artifactOrder = state.artifactOrder.filter(
    (id) => !HIDDEN_INLINE_LANGS.has(state.artifacts[id]?.lang ?? ""),
  );
  const artifacts = Object.fromEntries(
    artifactOrder.map((id) => [id, state.artifacts[id]]),
  );
  return { ...state, artifactOrder, artifacts };
}
