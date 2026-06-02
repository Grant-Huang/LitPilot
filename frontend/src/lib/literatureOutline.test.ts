import { describe, expect, it } from "vitest";
import { parseLiteratureOutline } from "@/lib/literatureOutline";

describe("parseLiteratureOutline", () => {
  it("parses valid outline json", () => {
    const raw = JSON.stringify({
      topic: "AI MOM",
      sections: [{ id: "s1", number: "1", title: "定义", desc: "框架" }],
      sub_topics: [],
    });
    const parsed = parseLiteratureOutline(raw);
    expect(parsed?.topic).toBe("AI MOM");
    expect(parsed?.sections).toHaveLength(1);
  });

  it("returns null for invalid json", () => {
    expect(parseLiteratureOutline("not json")).toBeNull();
  });
});
