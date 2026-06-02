import type { WorkflowGraphJson } from "@/lib/workflowGraph";

/** 侧栏「流程」：展示完整执行链（含 M2 结构化/大纲/分章/后处理），不再裁剪为 4 节点。 */
export function graphForPipelineDisplay(graph: WorkflowGraphJson): WorkflowGraphJson {
  return {
    ...graph,
    title: graph.title || "文献处理流水线",
  };
}
