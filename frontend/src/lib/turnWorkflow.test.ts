import { describe, expect, it } from "vitest";
import { buildTurnCompletionSummary } from "./turnCompletion";
import { buildTurnWorkflowFromTrace, deriveLiveFieldsFromStream } from "./turnWorkflow";
import type { StreamState } from "@meso.ai/ui";

describe("deriveLiveFieldsFromStream progress dedupe", () => {
  it("keeps heartbeat progress separate from brief assessment", () => {
    const stream = {
      status: "streaming",
      textContent: "",
      thinkContent: "模型思考…",
      extensionLog: [
        {
          payload: {
            name: "literature_progress",
            data: {
              stage: "understand",
              detail: "分析研究问题并生成检索规划…",
            },
          },
        },
        {
          payload: {
            name: "literature_brief_assessment",
            data: {
              core_research_questions: ["RQ1"],
              keywords: ["AI", "MOM"],
            },
          },
        },
      ],
      stages: [{ name: "理解研究问题", state: "active" }],
      toolCallOrder: [],
      toolCalls: {},
      workflowRunOrder: [],
      workflowRuns: {},
    } as unknown as StreamState;

    const fields = deriveLiveFieldsFromStream(stream);
    expect(fields.liveProgressDetail).toBe("分析研究问题并生成检索规划…");
    expect(fields.briefSummary).toContain("RQ：RQ1");
    expect(fields.processText).toContain("RQ：RQ1");
    expect(fields.processText).not.toContain("分析研究问题并生成检索规划");
  });
});

describe("buildTurnWorkflowFromTrace streaming layout", () => {
  it("does not create brief card from progress heartbeat alone", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [{ name: "理解研究问题", state: "active" }],
        tools: [],
        workflows: [],
        thinkContent: "正在分析…",
      },
      {
        streaming: true,
        extensions: [
          {
            name: "literature_progress",
            data: {
              stage: "understand",
              detail: "分析研究问题并生成检索规划…",
            },
          },
        ],
      },
    );
    expect(wf.cards.some((c) => c.type === "brief")).toBe(false);
    expect(wf.summary).toBe("理解研究问题");
    const understand = wf.cards.find((c) => c.type === "understand");
    expect(understand?.body).toBeUndefined();
  });

  it("creates brief card only from structured assessment", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [{ name: "Brief 评估", state: "done" }],
        tools: [],
        workflows: [],
      },
      {
        briefSummary: "RQ：foo\n关键词：bar",
      },
    );
    const brief = wf.cards.find((c) => c.type === "brief");
    expect(brief?.body).toContain("RQ：foo");
  });
});

describe("buildTurnCompletionSummary streaming headline", () => {
  it("shows stage-only headline while streaming", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [{ name: "理解研究问题", state: "active" }],
        tools: [],
        workflows: [],
      },
      { streaming: true },
    );
    const summary = buildTurnCompletionSummary(wf, { streaming: true });
    expect(summary.headline).toBe("当前：理解研究问题");
    expect(summary.headline).not.toContain("分析研究问题并生成检索规划");
  });
});
