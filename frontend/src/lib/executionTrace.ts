import type { StreamState, ToolCallState } from "@meso/ui";
import type { WorkflowNodeState } from "@meso/types";
import { describeToolAction, previewToolResult } from "@/lib/toolLabels";

export type SerializedToolStep = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: ToolCallState["status"];
  output?: string;
  error?: string;
  duration_ms?: number;
};

export type SerializedWorkflowStep = {
  node_id: string;
  name: string;
  state: WorkflowNodeState;
  title?: string;
  url?: string;
  error?: string;
  duration_ms?: number;
};

export type ExecutionTrace = {
  stages: { name: string; state: string }[];
  tools: SerializedToolStep[];
  workflows: SerializedWorkflowStep[];
  thinkContent?: string;
};

/** 将 msg_meta.think 合并进 execution_trace，供历史消息展示思考过程。 */
export function mergeThinkIntoTrace(
  trace: ExecutionTrace | undefined,
  think?: string,
): ExecutionTrace | undefined {
  const mergedThink = (think || trace?.thinkContent || "").trim();
  if (!trace && !mergedThink) return undefined;
  const base: ExecutionTrace = trace ?? {
    stages: [],
    tools: [],
    workflows: [],
  };
  if (!mergedThink) return base;
  return { ...base, thinkContent: mergedThink };
}

export type ProcessLine = {
  key: string;
  kind: "tool" | "workflow";
  status: "pending" | "running" | "done" | "error";
  title: string;
  preview?: string;
  detail?: string;
  duration_ms?: number;
};

export function collectExecutionTraceFromStream(
  stream: StreamState,
): ExecutionTrace {
  const tools: SerializedToolStep[] = [];
  for (const id of stream.toolCallOrder) {
    const tc = stream.toolCalls[id];
    if (!tc) continue;
    tools.push(serializeToolStep(tc));
  }

  const workflows: SerializedWorkflowStep[] = [];
  for (const runId of stream.workflowRunOrder) {
    const run = stream.workflowRuns[runId];
    if (!run) continue;
    for (const nodeId of run.nodeOrder) {
      const node = run.nodes[nodeId];
      if (!node) continue;
      if (nodeId === "fetch" && node.name === "fetch") continue;
      const meta = node.metadata ?? {};
      workflows.push({
        node_id: nodeId,
        name: node.name,
        state: node.state,
        title: String(meta.title ?? "").trim() || undefined,
        url: String(meta.url ?? "").trim() || undefined,
        error: String(meta.error ?? "").trim() || undefined,
        duration_ms: node.duration_ms,
      });
    }
  }

  const think = stream.thinkContent?.trim();
  return {
    stages: stream.stages.map((s) => ({ name: s.name, state: s.state })),
    tools,
    workflows,
    thinkContent: think || undefined,
  };
}

export function serializeToolStep(tc: ToolCallState): SerializedToolStep {
  return {
    id: tc.call.id,
    name: tc.call.name,
    args: (tc.call.args ?? {}) as Record<string, unknown>,
    status: tc.status,
    output: tc.result?.output,
    error: tc.result?.error,
    duration_ms: tc.result?.duration_ms,
  };
}

export function toolStepToState(step: SerializedToolStep): ToolCallState {
  return {
    call: {
      id: step.id,
      name: step.name,
      args: step.args,
      risk: "safe",
      provider: "api",
    },
    result: {
      tool_call_id: step.id,
      output: step.output ?? "",
      error: step.error,
      duration_ms: step.duration_ms,
    },
    status: step.status,
  };
}

function workflowTitle(step: SerializedWorkflowStep): string {
  const label =
    step.name === "web_fetch"
      ? "抓取网页"
      : step.name === "extract_citation" || step.name === "cite_extract"
        ? "引用抽取"
        : step.name.replace(/_/g, " ");
  if (step.title) return `${label}：${step.title}`;
  if (step.url) {
    try {
      return `${label}：${new URL(step.url).hostname}`;
    } catch {
      return `${label}：${step.url.slice(0, 48)}`;
    }
  }
  return label;
}

function workflowPreview(step: SerializedWorkflowStep): string {
  if (step.state === "error") {
    return step.error || "执行失败";
  }
  if (step.state === "active") return "执行中…";
  return "已完成";
}

function toolUrl(step: SerializedToolStep): string {
  return String(step.args?.url ?? "").trim();
}

/** 合并工具调用与工作流节点为单条时间线（去重同 URL 的重复失败项） */
export function buildProcessLines(trace: ExecutionTrace): ProcessLine[] {
  const lines: ProcessLine[] = [];
  const toolUrls = new Set(
    trace.tools.map(toolUrl).filter(Boolean),
  );

  for (const t of trace.tools) {
    const status =
      t.status === "pending" || t.status === "running"
        ? t.status
        : t.status === "error"
          ? "error"
          : "done";
    lines.push({
      key: `tool-${t.id}`,
      kind: "tool",
      status,
      title: describeToolAction({
        id: t.id,
        name: t.name,
        args: t.args,
        risk: "safe",
        provider: "api",
      }),
      preview: previewToolResult(t.output, t.error),
      detail: t.error || t.output,
      duration_ms: t.duration_ms,
    });
  }

  for (const w of trace.workflows) {
    const url = (w.url ?? "").trim();
    if (url && toolUrls.has(url)) continue;
    if (w.state === "skipped") continue;
    const status =
      w.state === "active"
        ? "running"
        : w.state === "error"
          ? "error"
          : "done";
    lines.push({
      key: `wf-${w.node_id}`,
      kind: "workflow",
      status,
      title: workflowTitle(w),
      preview: workflowPreview(w),
      detail: w.error,
      duration_ms: w.duration_ms,
    });
  }

  return lines;
}

export function traceHasProcessContent(trace: ExecutionTrace): boolean {
  return Boolean(
    trace.thinkContent ||
      trace.stages.length ||
      trace.tools.length ||
      trace.workflows.length,
  );
}
