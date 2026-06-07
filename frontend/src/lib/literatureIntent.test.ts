import { describe, expect, it } from "vitest";
import { formatLiteratureIntentLabel } from "./literatureIntent";

describe("literatureIntent", () => {
  it("maps known intents", () => {
    expect(formatLiteratureIntentLabel("append_urls")).toContain("追加");
    expect(formatLiteratureIntentLabel("review_refine")).toContain("修订");
    expect(formatLiteratureIntentLabel("subtopic_change")).toContain("子主题");
  });

  it("falls back to raw intent", () => {
    expect(formatLiteratureIntentLabel("unknown_x")).toBe("unknown_x");
  });
});
