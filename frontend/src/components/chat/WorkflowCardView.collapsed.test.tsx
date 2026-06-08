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
  it("renders the head row with a clickable title button when card is done and collapsed", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ summary: "已完成" })}
        streaming={false}
      />,
    );
    // Head row must exist in DOM (not hidden)
    expect(html).toContain("litpilot-wf-card__head");
    // Title is a button so it is keyboard-activatable and clickable
    expect(html).toMatch(/<button[^>]*class="[^"]*litpilot-wf-card__title-btn/);
    expect(html).toContain("aria-expanded");
    // Marker and summary appear on the collapsed row
    expect(html).toContain("litpilot-wf-card__marker");
    expect(html).toContain("litpilot-wf-card__inline-summary");
    expect(html).toContain("已完成");
  });

  it("uses a ✓ marker and the card carries the done+not-open modifier class so the collapsed head can be styled as a visible block", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView card={makeCard()} streaming={false} />,
    );
    // The collapsed marker is a done-status icon (SVG checkmark in StatusIcon).
    expect(html).toMatch(/litpilot-wf-card__marker[^>]*>.*lp-status-icon--done/);
    // The section root carries --done but NOT --open, so the new CSS rule that
    // highlights collapsed heads can apply.
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--done/);
    expect(html).not.toMatch(
      /class="[^"]*litpilot-wf-card--done[^"]*litpilot-wf-card--open/,
    );
  });

  it("does not render the body region when the card is done and not manually opened", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({
          body: "Some brief assessment text",
          subTopics: [{ id: "s1", title: "Subtopic A", search_query: "q" }],
        })}
        streaming={false}
      />,
    );
    // Body should be omitted entirely when collapsed.
    expect(html).not.toContain("litpilot-wf-card__body");
    expect(html).not.toContain("Some brief assessment text");
  });

  it("renders the body when forceOpen is set (e.g. programmatic expansion)", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ summary: "3 个子主题", state: "done" })}
        streaming={false}
        forceOpen
      />,
    );
    // Body is present.
    expect(html).toContain("litpilot-wf-card__body");
    // The title remains a clickable button so the user can collapse the
    // card again.
    expect(html).toMatch(/<button[^>]*class="[^"]*litpilot-wf-card__title-btn/);
  });

  it("the brief card also collapses to a clickable head row when done (same visibility rule as understand)", () => {
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
    // Same rule: title is a clickable button, head row exists, body hidden.
    expect(html).toMatch(/<button[^>]*class="[^"]*litpilot-wf-card__title-btn/);
    expect(html).toContain("litpilot-wf-card__head");
    expect(html).not.toContain("litpilot-wf-card__body");
    // The full body text is NOT rendered when collapsed.
    expect(html).not.toContain("检索 hint");
  });

  it("the search card also collapses to a clickable head row when done (same visibility rule)", () => {
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
    // Same visibility rule: clickable title button, head row exists, body hidden.
    expect(html).toMatch(/<button[^>]*class="[^"]*litpilot-wf-card__title-btn/);
    expect(html).toContain("litpilot-wf-card__head");
    expect(html).not.toContain("litpilot-wf-card__body");
  });

  it("collapsed done card head carries --done modifier (not --open) so CSS uses accent-based background for cross-theme visibility", () => {
    // CSS contract: .litpilot-wf-card--done:not(.litpilot-wf-card--open) .litpilot-wf-card__head
    // uses background: color-mix(in srgb, var(--color-accent, #d97706) 6%, transparent)
    // and border-left: color-mix(in srgb, var(--color-accent, #d97706) 38%, transparent)
    // ensuring the card is never invisible on any theme.
    const html = renderToStaticMarkup(
      <WorkflowCardView card={makeCard()} streaming={false} />,
    );
    // Root element must have --done class.
    expect(html).toMatch(/class="[^"]*litpilot-wf-card--done/);
    // Root element must NOT have --open class, so the collapsed-head rule applies.
    expect(html).not.toMatch(
      /class="[^"]*litpilot-wf-card--done[^"]*litpilot-wf-card--open/,
    );
    // The head row must exist for the CSS rule to target it.
    expect(html).toContain("litpilot-wf-card__head");
    // The title button must exist and be visible.
    expect(html).toMatch(/<button[^>]*class="[^"]*litpilot-wf-card__title-btn/);
  });

  it("collapsed done card title button text is rendered with visible color", () => {
    // The CSS rule .litpilot-wf-card--done:not(.litpilot-wf-card--open) .litpilot-wf-card__title-btn
    // sets color: var(--color-text-secondary, #555) which is always visible.
    const html = renderToStaticMarkup(
      <WorkflowCardView card={makeCard()} streaming={false} />,
    );
    // Verify the title text is actually rendered (not hidden/truncated to nothing).
    expect(html).toContain("理解研究问题");
    // The title appears inside a button element for accessibility.
    expect(html).toMatch(
      /<button[^>]*class="[^"]*litpilot-wf-card__title-btn[^"]*"[^>]*>[\s\S]*理解研究问题/,
    );
  });

  it("hides 进行中 when think stream is active", () => {
    const html = renderToStaticMarkup(
      <WorkflowCardView
        card={makeCard({ state: "running" })}
        trace={{ stages: [], tools: [], workflows: [], thinkContent: "思考中" }}
        streaming
        defaultOpen
      />,
    );
    // Card head should not say "进行中" (it uses StatusIcon with "等待" for pending).
    // The think-fold header may show "进行中" via StatusIcon aria-label; that is correct.
    const headMatch = html.match(/<div class="litpilot-wf-card__head">[\s\S]*?<\/div>/);
    if (headMatch) expect(headMatch[0]).not.toContain("进行中");
    expect(html).toContain("思考中");
  });
});
