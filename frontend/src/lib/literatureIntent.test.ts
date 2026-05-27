import { describe, expect, it } from "vitest";
import { formatLiteratureIntentLabel } from "./literatureIntent";

describe("literatureIntent", () => {
  it("maps known intents", () => {
    expect(formatLiteratureIntentLabel("supplement")).toContain("补充");
    expect(formatLiteratureIntentLabel("refine_gen")).toContain("要求");
    expect(formatLiteratureIntentLabel("synthesis_matrix")).toContain("矩阵");
  });

  it("falls back to raw intent", () => {
    expect(formatLiteratureIntentLabel("unknown_x")).toBe("unknown_x");
  });
});
