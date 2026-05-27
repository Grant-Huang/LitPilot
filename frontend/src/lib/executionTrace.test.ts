import { describe, expect, it } from "vitest";
import { createInitialStreamState } from "@meso.ai/ui";
import {
  buildProcessLines,
  collectExecutionTraceFromStream,
  mergeThinkIntoTrace,
} from "./executionTrace";

describe("executionTrace", () => {
  it("收集阶段、工具调用与工作流节点", () => {
    const stream = createInitialStreamState();
    stream.status = "streaming";
    stream.stages = [{ name: "文献检索", state: "done" }];
    stream.toolCallOrder = ["tc1"];
    stream.toolCalls = {
      tc1: {
        call: {
          id: "tc1",
          name: "web_search",
          args: { query: "MOM AI" },
          risk: "safe",
          provider: "api",
        },
        status: "done",
        result: { tool_call_id: "tc1", output: '{"hits":3}' },
      },
    };
    stream.workflowRunOrder = ["run1"];
    stream.workflowRuns = {
      run1: {
        run_id: "run1",
        nodeOrder: ["fetch", "fetch_0"],
        nodes: {
          fetch: {
            node_id: "fetch",
            run_id: "run1",
            name: "fetch",
            state: "done",
          },
          fetch_0: {
            node_id: "fetch_0",
            run_id: "run1",
            name: "web_fetch",
            state: "done",
            parent_id: "fetch",
            metadata: {
              url: "https://arxiv.org/abs/1",
              title: "Paper A",
            },
          },
        },
      },
    };

    const trace = collectExecutionTraceFromStream(stream);
    expect(trace.stages).toHaveLength(1);
    expect(trace.tools).toHaveLength(1);
    expect(trace.workflows).toHaveLength(1);
    expect(trace.workflows[0].state).toBe("done");

    const lines = buildProcessLines(trace);
    expect(lines.some((l) => l.title.includes("检索学术文献"))).toBe(true);
    expect(lines.some((l) => l.title.includes("Paper A"))).toBe(true);
  });

  it("同 URL 失败时工具与工作流节点不重复", () => {
    const trace = collectExecutionTraceFromStream({
      ...createInitialStreamState(),
      toolCallOrder: ["tc2"],
      toolCalls: {
        tc2: {
          call: {
            id: "tc2",
            name: "web_fetch",
            args: { url: "https://example.com/x" },
            risk: "safe",
            provider: "api",
          },
          status: "error",
          result: {
            tool_call_id: "tc2",
            output: "",
            error: "timeout",
          },
        },
      },
      workflowRunOrder: ["r"],
      workflowRuns: {
        r: {
          run_id: "r",
          nodeOrder: ["n1"],
          nodes: {
            n1: {
              node_id: "n1",
              run_id: "r",
              name: "web_fetch",
              state: "error",
              metadata: { url: "https://example.com/x", error: "timeout" },
            },
          },
        },
      },
    });
    const lines = buildProcessLines(trace);
    const fetchLines = lines.filter((l) => l.title.includes("抓取"));
    expect(fetchLines).toHaveLength(1);
  });

  it("mergeThinkIntoTrace 合并 msg_meta.think 与 execution_trace", () => {
    const merged = mergeThinkIntoTrace(
      { stages: [], tools: [], workflows: [] },
      "研究主题：MES",
    );
    expect(merged?.thinkContent).toBe("研究主题：MES");

    const onlyThink = mergeThinkIntoTrace(undefined, "仅思考");
    expect(onlyThink?.thinkContent).toBe("仅思考");
    expect(onlyThink?.stages).toEqual([]);
  });
});
