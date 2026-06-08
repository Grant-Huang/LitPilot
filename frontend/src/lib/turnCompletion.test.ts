import { describe, expect, it } from "vitest";
import { formatToolLogLine, humanizeDurationMs } from "./toolLabels";
import { buildTurnCompletionSummary, summarizeWorkflowCard } from "./turnCompletion";
import { buildTurnWorkflowFromTrace } from "./turnWorkflow";
import { filterVisibleWorkflowSteps } from "./workflowStepFilter";

describe("humanizeDurationMs", () => {
  it("formats seconds for long durations", () => {
    expect(humanizeDurationMs(21045)).toBe("21s");
  });
});

describe("formatToolLogLine", () => {
  it("merges search query and hits into one line", () => {
    const line = formatToolLogLine(
      {
        id: "1",
        name: "web_search",
        args: { query: "AI MOM", provider: "semantic_scholar" },
        risk: "safe",
        provider: "api",
      },
      {
        output: JSON.stringify({ hits: 5, answer: "" }),
        duration_ms: 21045,
      },
      "done",
    );
    expect(line.primary).toContain("AI MOM");
    expect(line.outcome).toContain("找到 5 篇文献");
    expect(line.outcome).toContain("21s");
    expect(line.rawDetail).toBeNull();
  });
});

describe("buildTurnCompletionSummary", () => {
  it("builds headline from extensions and trace", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [{ name: "文献检索", state: "done" }],
        tools: [
          {
            id: "s1",
            name: "web_search",
            args: {},
            status: "done",
          },
        ],
        workflows: [],
      },
      {
        extensions: [
          {
            name: "literature_subtopic_filter_done",
            data: { subtopic_id: "st1", kept_count: 7 },
          },
          {
            name: "literature_subtopic_filter_done",
            data: { subtopic_id: "st2", kept_count: 5 },
          },
        ],
      },
    );
    const summary = buildTurnCompletionSummary(wf, {
      trace: {
        stages: [],
        tools: [
          {
            id: "s1",
            name: "web_search",
            args: {},
            status: "done",
          },
        ],
        workflows: [],
      },
      extensions: [
        {
          name: "literature_search_merge",
          data: { deduped: 12, raw_total: 20 },
        },
      ],
      hasReview: true,
    });
    expect(summary.headline).toContain("纳入 12 篇");
    expect(summary.headline).toContain("综述已生成");
    expect(summary.brief).toContain("右侧面板");
  });

  it("summarizes fetch card from trace tools", () => {
    const summary = summarizeWorkflowCard(
      {
        id: "f",
        type: "fetch",
        title: "抓取网页",
        state: "done",
        steps: [],
      },
      {
        trace: {
          stages: [],
          tools: [
            { id: "1", name: "web_fetch", args: {}, status: "done" },
            { id: "2", name: "web_fetch", args: {}, status: "error" },
          ],
          workflows: [],
        },
      },
    );
    expect(summary).toBe("1 篇 · 1 失败");
  });

  it("reads merged hits from persisted search card summary", () => {
    const wf = {
      turnIndex: 1,
      intent: "new_topic",
      summary: "",
      cards: [
        {
          id: "search",
          type: "search" as const,
          title: "文献检索",
          state: "done" as const,
          summary: "纳入 9 篇",
          steps: [],
        },
      ],
    };
    const summary = buildTurnCompletionSummary(wf, {});
    expect(summary.headline).toContain("纳入 9 篇");
  });

  it("appends weak subtopic brief from filter extension", () => {
    const wf = buildTurnWorkflowFromTrace(
      {
        stages: [],
        tools: [
          { id: "s1", name: "web_search", args: {}, status: "done" },
          { id: "s2", name: "web_search", args: {}, status: "done" },
        ],
        workflows: [],
      },
      {
        extensions: [
          {
            name: "literature_subtopic_plan",
            data: {
              subtopics: [
                { id: "st1", title: "子主题 A", search_query: "q1" },
                { id: "st2", title: "子主题 B", search_query: "q2" },
              ],
            },
          },
          {
            name: "literature_subtopic_filter_done",
            data: { subtopic_id: "st1", kept_count: 6 },
          },
          {
            name: "literature_subtopic_filter_done",
            data: { subtopic_id: "st2", kept_count: 1 },
          },
        ],
      },
    );
    const summary = buildTurnCompletionSummary(wf, {
      trace: {
        stages: [],
        tools: [
          { id: "s1", name: "web_search", args: {}, status: "done" },
          { id: "s2", name: "web_search", args: {}, status: "done" },
        ],
        workflows: [],
      },
      extensions: [
        {
          name: "literature_subtopic_plan",
          data: {
            subtopics: [
              { id: "st1", title: "子主题 A", search_query: "q1" },
              { id: "st2", title: "子主题 B", search_query: "q2" },
            ],
          },
        },
        {
          name: "literature_subtopic_filter_done",
          data: { subtopic_id: "st1", kept_count: 6 },
        },
        {
          name: "literature_subtopic_filter_done",
          data: { subtopic_id: "st2", kept_count: 1 },
        },
      ],
      hasReview: true,
    });
    expect(summary.brief).toContain("子主题 B");
    expect(summary.brief).toContain("修改子主题");
  });
});

describe("filterVisibleWorkflowSteps", () => {
  it("drops pass_start when search tool completed", () => {
    const steps = filterVisibleWorkflowSteps([
      {
        key: "ext-literature_search_pass_start-1",
        kind: "inline",
        title: "检索中：foo",
        status: "running",
      },
      {
        key: "tool-x-0",
        kind: "tool",
        title: "检索学术文献（1/1）：foo",
        status: "done",
      },
    ]);
    expect(steps.some((s) => s.key.includes("pass_start"))).toBe(false);
  });
});
