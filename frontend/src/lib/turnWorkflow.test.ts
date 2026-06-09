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

  it("pins understand think via literature_phase_think extension", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [
          { name: "理解研究问题", state: "done" },
          { name: "文献检索", state: "running" },
        ],
        tools: [],
        workflows: [],
        thinkContent: "理解阶段解说…\n\n检索阶段解说…",
      },
      {
        streaming: true,
        extensions: [
          {
            name: "literature_phase_think",
            data: { stage: "understand", content: "理解阶段解说…" },
          },
        ],
      },
    );
    const understand = wf.cards.find((c) => c.type === "understand");
    expect(understand?.pinnedThink).toBe("理解阶段解说…");
    expect(understand?.state).toBe("done");
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

describe("buildTurnWorkflowFromTrace canonical card order", () => {
  it("sorts cards into understand → brief → search → fetch order even if backend stages arrive shuffled", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        // Intentionally out-of-order: fetch arrives before search and brief
        stages: [
          { name: "理解研究问题", state: "done" },
          { name: "抓取全文", state: "done" },
          { name: "评估", state: "done" },
          { name: "文献检索", state: "done" },
        ],
        tools: [],
        workflows: [],
      },
      { streaming: false },
    );
    const types = wf.cards.map((c) => c.type);
    const understandIdx = types.indexOf("understand");
    const briefIdx = types.indexOf("brief");
    const searchIdx = types.indexOf("search");
    const fetchIdx = types.indexOf("fetch");
    expect(understandIdx).toBeGreaterThanOrEqual(0);
    expect(briefIdx).toBeGreaterThan(understandIdx);
    expect(searchIdx).toBeGreaterThan(briefIdx);
    expect(fetchIdx).toBeGreaterThan(searchIdx);
  });

  it("promotes lingering running cards to done when streaming=false", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [
          { name: "理解研究问题", state: "done" },
          { name: "文献检索", state: "active" },
          { name: "抓取全文", state: "done" },
        ],
        tools: [],
        workflows: [],
      },
      { streaming: false },
    );
    const search = wf.cards.find((c) => c.type === "search");
    expect(search?.state).toBe("done");
  });

  it("uses 研究计划 as the brief card title (not Brief 评估)", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [{ name: "Brief 评估", state: "done" }],
        tools: [],
        workflows: [],
      },
      { streaming: false },
    );
    const brief = wf.cards.find((c) => c.type === "brief");
    expect(brief?.title).toBe("研究计划");
  });
});
