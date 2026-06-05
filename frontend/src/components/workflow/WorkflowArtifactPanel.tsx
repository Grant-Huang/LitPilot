"use client";

import type { WorkflowRunState } from "@meso.ai/types";
import type { WorkflowGraphJson } from "@/lib/workflowGraph";
import {
  buildPipelineStatusHint,
  type StageSnapshot,
} from "@/lib/pipelineStatusHint";
import { WorkflowNodeList } from "./WorkflowNodeList";

type Props = {
  graph: WorkflowGraphJson;
  workflowRuns?: WorkflowRunState[];
  stages?: StageSnapshot[];
};

/** 以步骤列表为主展示执行进度；比 SVG DAG 更易读，且可随 M2 动态章节扩展。 */
export function WorkflowArtifactPanel({ graph, stages = [] }: Props) {
  const doneCount = graph.nodes.filter(
    (n) => n.status === "done" || n.status === "skipped",
  ).length;
  const total = graph.nodes.length;
  const hint = buildPipelineStatusHint(graph, stages);

  return (
    <div className="stock-wf-artifact stock-wf-artifact--pipeline">
      <div className="stock-wf-artifact__header">
        <span className="stock-wf-artifact__title">{graph.title}</span>
        <span className="stock-wf-pipeline__progress">
          {doneCount}/{total} 步
        </span>
      </div>
      <p className="stock-wf-pipeline__hint" title={hint}>
        {hint}。检索与理解在左侧思考区；本列表为抓取之后的处理链。
      </p>
      <WorkflowNodeList graph={graph} />
    </div>
  );
}
