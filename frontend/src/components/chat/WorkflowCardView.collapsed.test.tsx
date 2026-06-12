import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkflowCardView } from "./WorkflowCardView";
import type { WorkflowCard } from "@/lib/turnWorkflow";

function makeCard(overrides: Partial<WorkflowCard> = {}): WorkflowCard {
  return {
    id: "card-understand-test",
    type: "understand",
    title: "理解研究问题",
    state: "done",
    steps: [],
    ...overrides,
  };
}

describe("WorkflowCardView collapsed head visibility", () => {
  it("renders the head row as a clickable element when card is done and collapsed", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ summary: "已完成" })}
        streaming={false}
      />,
    );
    expect(html).toContain("litpilot-wf-card__head");
    expect(html).toContain("aria-expanded");
    expect(html).toContain("litpilot-wf-card__marker");
    expect(html).toContain("已完成");
  });

  it("uses a done marker and the card carries the done modifier class without open", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView card={makeCard()} streaming={false} />,
    );
    expect(html).toMatch(/litpilot-wf-card__marker[^>]*>.*lp-status-icon--done/);
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--done/);
    expect(html).not.toMatch(
      /class="[^"]*litpilot-wf-card--done[^"]*litpilot-wf-card--open/,
    );
  });

  it("keeps the body collapsed (no open modifier) when the card is done and not manually opened", () => {
    // 折叠改由 CSS（grid-rows 0fr）实现：body 仍在 DOM 中，但卡片不带 --open。
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({
          body: "Some brief assessment text",
          subTopics: [{ id: "s1", title: "Subtopic A", search_query: "q" }],
        })}
        streaming={false}
      />,
    );
    expect(html).toContain("litpilot-wf-card__body-wrap");
    expect(html).not.toMatch(/class="[^"]*litpilot-wf-card--open/);
  });

  it("renders the body when forceOpen is set", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ summary: "3 个子主题", state: "done" })}
        streaming={false}
        forceOpen
      />,
    );
    expect(html).toContain("litpilot-wf-card__body");
  });

  it("auto-expands a running streaming card and shows its tool steps in the body", () => {
    // 克制叙事：当前运行阶段自动展开，直接展示步骤，而非折叠头里的一行轮播摘要。
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({
          type: "fetch",
          title: "抓取全文",
          state: "running",
          steps: [
            { key: "tool-1", kind: "tool", title: "抓取：paper A", status: "done", duration_ms: 3200 },
            { key: "tool-2", kind: "tool", title: "抓取：paper B", status: "running" },
          ],
        })}
        streaming
      />,
    );
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--open/);
    expect(html).toContain("抓取：paper B");
  });

  it("shows card summary in collapsed head when card is done", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ summary: "纳入 47 篇", state: "done" })}
        streaming={false}
      />,
    );
    expect(html).toContain("纳入 47 篇");
  });

  it("the brief card also collapses to a clickable head row when done", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({
          type: "brief",
          title: "研究问题评估",
          state: "done",
          body: "RQ line 1\n关键词: ...\n检索 hint: ...",
        })}
        streaming={false}
      />,
    );
    expect(html).toContain("litpilot-wf-card__head");
    expect(html).not.toMatch(/class="[^"]*litpilot-wf-card--open/);
  });

  it("the search card also collapses to a clickable head row when done", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({
          type: "search",
          title: "检索文献",
          state: "done",
          subTopics: [{ id: "topic-a", title: "Topic A", search_query: "Topic A" }],
        })}
        streaming={false}
      />,
    );
    expect(html).toContain("litpilot-wf-card__head");
    expect(html).not.toMatch(/class="[^"]*litpilot-wf-card--open/);
  });

  it("collapsed done card head carries done modifier for CSS styling", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView card={makeCard()} streaming={false} />,
    );
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--done/);
    expect(html).not.toMatch(
      /class="[^"]*litpilot-wf-card--done[^"]*litpilot-wf-card--open/,
    );
    expect(html).toContain("litpilot-wf-card__head");
  });

  it("auto-expands a running streaming card and surfaces live think content", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ state: "running" })}
        trace={{ stages: [], tools: [], workflows: [], thinkContent: "思考中" }}
        streaming
      />,
    );
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--open/);
    expect(html).toContain("思考中");
  });
});
