import type { StreamState } from "@meso/ui";
import type { WorkflowRunState } from "@meso/types";

export function workflowRunsFromStream(state: StreamState): WorkflowRunState[] {
  return state.workflowRunOrder
    .map((id) => state.workflowRuns[id])
    .filter((r): r is WorkflowRunState => Boolean(r));
}
