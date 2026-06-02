import { describe, expect, it } from "vitest";
import { splitHelpBody } from "@/content/help/renderHelpBody";

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
