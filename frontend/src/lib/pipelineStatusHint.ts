import type { WorkflowGraphJson } from "@/lib/workflowGraph";

export type StageSnapshot = { name: string; state: string };

/** 不在右侧 DAG 中、但在 stream.stages 里推进的前置阶段 */
const PRE_PIPELINE_STAGE_NAMES = new Set([
  "理解研究问题",
  "分析用户意图",
  "文献检索",
  "等待澄清",
  "继续撰写",
]);

function activeStage(stages: StageSnapshot[]): StageSnapshot | undefined {
  for (let i = stages.length - 1; i >= 0; i -= 1) {
    if (stages[i].state === "active") return stages[i];
  }
  return undefined;
}

function nextPendingNode(graph: WorkflowGraphJson) {
  return graph.nodes.find((n) => n.status === "pending");
}

/**
 * 据实生成执行计划顶部提示：结合 DAG 节点状态与左侧 stage 时间线。
 */
export function buildPipelineStatusHint(
  graph: WorkflowGraphJson,
  stages: StageSnapshot[],
): string {
  const activeNode = graph.nodes.find((n) => n.status === "active");
  if (activeNode) {
    return `当前：${activeNode.label}`;
  }

  const doneCount = graph.nodes.filter(
    (n) => n.status === "done" || n.status === "skipped",
  ).length;
  const total = graph.nodes.length;
  if (total > 0 && doneCount >= total) {
    return "本回合流程已完成";
  }

  const stage = activeStage(stages);
  if (stage) {
    if (PRE_PIPELINE_STAGE_NAMES.has(stage.name) && doneCount === 0) {
      return `前置：${stage.name}（左侧思考区同步展示）`;
    }
    return `同步阶段：${stage.name}`;
  }

  const next = nextPendingNode(graph);
  if (doneCount > 0 && next) {
    return `下一步：${next.label}`;
  }

  if (doneCount === 0) {
    const last = stages[stages.length - 1];
    if (last?.state === "done" && PRE_PIPELINE_STAGE_NAMES.has(last.name) && next) {
      return `即将开始：${next.label}`;
    }
    if (last?.state === "skipped" && next) {
      return `已跳过前置检索，即将：${next.label}`;
    }
    return "计划已就绪，抓取链尚未开始";
  }

  return "处理链执行中…";
}
