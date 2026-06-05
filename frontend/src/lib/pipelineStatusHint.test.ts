import { describe, expect, it } from "vitest";
import { buildPipelineStatusHint } from "./pipelineStatusHint";
import type { WorkflowGraphJson } from "./workflowGraph";

const graph = (nodes: WorkflowGraphJson["nodes"]): WorkflowGraphJson => ({
  version: "1.0",
  id: "literature-agent",
  title: "文献综述执行计划",
  nodes,
  edges: [],
});

describe("buildPipelineStatusHint", () => {
  it("shows pre-pipeline stage when DAG not started", () => {
    const g = graph([
      { id: "fetch", label: "抓取全文", kind: "fetch", status: "pending" },
    ]);
    const hint = buildPipelineStatusHint(g, [
      { name: "文献检索", state: "active" },
    ]);
    expect(hint).toContain("前置：文献检索");
    expect(hint).not.toContain("等待执行");
  });

  it("shows active pipeline node", () => {
    const g = graph([
      { id: "fetch", label: "抓取全文", kind: "fetch", status: "active" },
      { id: "cite_extract", label: "引用抽取", kind: "cite_extract", status: "pending" },
    ]);
    expect(buildPipelineStatusHint(g, [])).toBe("当前：抓取全文");
  });

  it("shows next step after partial progress", () => {
    const g = graph([
      { id: "fetch", label: "抓取全文", kind: "fetch", status: "done" },
      { id: "cite_extract", label: "引用抽取", kind: "cite_extract", status: "pending" },
    ]);
    expect(buildPipelineStatusHint(g, [])).toBe("下一步：引用抽取");
  });
});
