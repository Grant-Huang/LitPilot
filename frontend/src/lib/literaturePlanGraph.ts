import type { WorkflowGraphJson } from "@/lib/workflowGraph";

/** Static DAG template; live node status comes from workflow_node SSE. */
export const LITERATURE_PLAN_GRAPH: WorkflowGraphJson = {
  version: "1.0",
  id: "literature-agent",
  title: "文献处理流水线",
  nodes: [
    {
      id: "fetch",
      label: "抓取全文",
      kind: "fetch",
      status: "pending",
      description: "native 直连 HTTP / web_fetch",
    },
    {
      id: "cite_extract",
      label: "引用抽取",
      kind: "cite_extract",
      status: "pending",
      description: "引用元数据",
    },
    {
      id: "generate",
      label: "综述生成",
      kind: "llm",
      status: "pending",
      description: "LLM 综合写作",
    },
    {
      id: "deliver",
      label: "交付",
      kind: "deliver",
      status: "pending",
      description: "保存引用与 Artifact",
    },
  ],
  edges: [
    { id: "e1", source: "fetch", target: "cite_extract" },
    { id: "e2", source: "cite_extract", target: "generate" },
    { id: "e3", source: "generate", target: "deliver" },
  ],
};
