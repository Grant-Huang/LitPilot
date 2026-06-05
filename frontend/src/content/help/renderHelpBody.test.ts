import { describe, expect, it } from "vitest";
import { renderHelpBodyHtml, splitHelpBody } from "@/content/help/renderHelpBody";

describe("splitHelpBody", () => {
  it("splits internal help links", () => {
    const parts = splitHelpBody("见 [[tavily-search|Tavily 说明]] 详情。");
    expect(parts).toHaveLength(3);
    expect(parts[1]).toEqual({
      kind: "link",
      id: "tavily-search",
      label: "Tavily 说明",
    });
  });
});

describe("renderHelpBodyHtml", () => {
  it("keeps inline links inside one paragraph", () => {
    const html = renderHelpBodyHtml(
      "多 aspect 写法（见 [[research-brief|如何写研究问题]]）。",
    );
    expect(html).toMatch(/^<p>/);
    expect(html).toContain("data-help-page=\"research-brief\"");
    expect(html).toContain("如何写研究问题");
    expect(html).toContain("）。</p>");
    expect(html.match(/<p>/g)?.length).toBe(1);
  });

  it("wraps tables for horizontal scroll", () => {
    const html = renderHelpBodyHtml(
      "| A | B |\n| --- | --- |\n| 1 | 2 |",
    );
    expect(html).toContain("help-center__table-wrap");
    expect(html).toContain("<table>");
  });

  it("renders fenced code blocks", () => {
    const html = renderHelpBodyHtml("```\n其一，foo\n其二，bar\n```");
    expect(html).toContain("help-center__pre");
    expect(html).toContain("其一，foo");
  });
});
