"use client";

import type { WorkflowRunState } from "@meso.ai/types";
import type { WorkflowGraphJson } from "@/lib/workflowGraph";
import { WorkflowNodeList } from "./WorkflowNodeList";

type Props = {
  graph: WorkflowGraphJson;
  workflowRuns?: WorkflowRunState[];
};

/** 以步骤列表为主展示执行进度；比 SVG DAG 更易读，且可随 M2 动态章节扩展。 */
export function WorkflowArtifactPanel({ graph }: Props) {
  const active = graph.nodes.find((n) => n.status === "active");
  const doneCount = graph.nodes.filter((n) => n.status === "done").length;
  const total = graph.nodes.length;

  return (
    <div className="stock-wf-artifact stock-wf-artifact--pipeline">
      <div className="stock-wf-artifact__header">
        <span className="stock-wf-artifact__title">{graph.title}</span>
        <span className="stock-wf-pipeline__progress">
          {doneCount}/{total} 步
        </span>
      </div>
      <p className="stock-wf-pipeline__hint">
        {active
          ? `当前：${active.label}`
          : doneCount >= total
            ? "本回合流程已完成"
            : "等待执行…"}
        。检索与理解阶段在左侧思考区展示；此处聚焦抓取之后的处理链。
      </p>
      <WorkflowNodeList graph={graph} />
    </div>
  );
}
