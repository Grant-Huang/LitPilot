import { describe, expect, it } from "vitest";
import {
  parseThinkSegments,
  THINK_SYS_END,
  THINK_SYS_START,
} from "@/lib/thinkContent";

describe("parseThinkSegments", () => {
  it("parses model and system segments", () => {
    const raw = `先分析主题。${THINK_SYS_START}已跳过 Tavily${THINK_SYS_END}\n再补充。`;
    const segs = parseThinkSegments(raw);
    expect(segs).toHaveLength(3);
    expect(segs[0].kind).toBe("model");
    expect(segs[1].kind).toBe("system");
    expect(segs[1].text).toBe("已跳过 Tavily");
  });

  it("returns single model segment when no system markers", () => {
    const segs = parseThinkSegments("仅模型解说内容");
    expect(segs).toEqual([{ kind: "model", text: "仅模型解说内容" }]);
  });

  it("handles empty content", () => {
    expect(parseThinkSegments("")).toEqual([]);
    expect(parseThinkSegments("   ")).toEqual([]);
  });

  it("handles multiple system lines", () => {
    const raw = [
      `${THINK_SYS_START}开始抓取${THINK_SYS_END}`,
      "模型段落",
      `${THINK_SYS_START}已跳过 Tavily${THINK_SYS_END}`,
    ].join("");
    const segs = parseThinkSegments(raw);
    expect(segs.filter((s) => s.kind === "system")).toHaveLength(2);
    expect(segs.some((s) => s.kind === "model" && s.text.includes("模型段落"))).toBe(
      true,
    );
  });
});
