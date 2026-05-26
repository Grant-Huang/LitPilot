"use client";

import type { WorkflowRunState } from "@meso/types";
import type { WorkflowGraphJson } from "@/lib/workflowGraph";
import { WorkflowGraphView } from "./WorkflowGraphView";
import { WorkflowNodeList } from "./WorkflowNodeList";

type Props = {
  graph: WorkflowGraphJson;
  workflowRuns?: WorkflowRunState[];
};

export function WorkflowArtifactPanel({ graph, workflowRuns = [] }: Props) {
  return (
    <div className="stock-wf-artifact">
      <div className="stock-wf-artifact__header">
        <span className="stock-wf-artifact__title">{graph.title}</span>
      </div>
      <div className="stock-wf-artifact__dual">
        <div className="stock-wf-artifact__graph">
          <WorkflowGraphView graph={graph} />
        </div>
        <WorkflowNodeList graph={graph} />
      </div>
    </div>
  );
}
