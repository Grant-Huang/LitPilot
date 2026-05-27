import { describe, expect, it } from "vitest";
import { parseUrlsFromText } from "./parseUrlList";

describe("parseUrlsFromText", () => {
  it("respects limit from settings cap", () => {
    const many = Array.from({ length: 65 }, (_, i) => `https://example.com/p${i}`).join(
      "\n",
    );
    const r = parseUrlsFromText(many, 50);
    expect(r.urls).toHaveLength(50);
    expect(r.totalFound).toBe(65);
    expect(r.truncated).toBe(true);
  });

  it("does not cap at legacy 20", () => {
    const many = Array.from({ length: 30 }, (_, i) => `https://example.com/x${i}`).join(
      " ",
    );
    const r = parseUrlsFromText(many, 50);
    expect(r.urls).toHaveLength(30);
    expect(r.truncated).toBe(false);
  });
});
