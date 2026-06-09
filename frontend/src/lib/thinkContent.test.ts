import { describe, expect, it } from "vitest";
import {
  dropStaleSysSegments,
  parseThinkSegments,
  splitModelByEnum,
  THINK_SYS_END,
  THINK_SYS_START,
} from "@/lib/thinkContent";

describe("parseThinkSegments", () => {
  it("parses model and system segments", () => {
    const raw = `先分析主题。${THINK_SYS_START}已跳过 web_search${THINK_SYS_END}\n再补充。`;
    const segs = parseThinkSegments(raw);
    expect(segs).toHaveLength(3);
    expect(segs[0].kind).toBe("model");
    expect(segs[1].kind).toBe("system");
    expect(segs[1].text).toBe("已跳过 web_search");
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
      `${THINK_SYS_START}已跳过 web_search${THINK_SYS_END}`,
    ].join("");
    const segs = parseThinkSegments(raw);
    expect(segs.filter((s) => s.kind === "system")).toHaveLength(2);
    expect(segs.some((s) => s.kind === "model" && s.text.includes("模型段落"))).toBe(
      true,
    );
  });

  it("strips 【sys】/[sys] bracket variants from leaked content", () => {
    const raw = "正文【sys】测试【/sys】尾巴[sys]ascii[/sys]";
    const segs = parseThinkSegments(raw);
    const joined = segs.map((s) => s.text).join("|");
    expect(joined).not.toContain("【sys】");
    expect(joined).not.toContain("【/sys】");
    expect(joined).not.toContain("[sys]");
    expect(joined).not.toContain("[/sys]");
  });
});

describe("dropStaleSysSegments", () => {
  it("drops sys segments that are followed by a model segment", () => {
    const segs = [
      { kind: "system" as const, text: "正在整理结构化检索规划" },
      { kind: "model" as const, text: "该研究主题围绕…" },
    ];
    const result = dropStaleSysSegments(segs);
    expect(result).toHaveLength(1);
    expect(result[0].kind).toBe("model");
  });

  it("keeps trailing sys segments with no model after them", () => {
    const segs = [
      { kind: "model" as const, text: "已完成阶段一" },
      { kind: "system" as const, text: "正在生成下一节" },
    ];
    const result = dropStaleSysSegments(segs);
    expect(result).toHaveLength(2);
    expect(result[1].kind).toBe("system");
    expect(result[1].text).toBe("正在生成下一节");
  });

  it("drops only superseded sys segments, keeps live trailing hint", () => {
    const segs = [
      { kind: "system" as const, text: "正在 step 1" },
      { kind: "model" as const, text: "step 1 输出" },
      { kind: "system" as const, text: "正在 step 2" },
      { kind: "model" as const, text: "step 2 输出" },
      { kind: "system" as const, text: "正在 step 3" },
    ];
    const result = dropStaleSysSegments(segs);
    expect(result.map((s) => s.text)).toEqual([
      "step 1 输出",
      "step 2 输出",
      "正在 step 3",
    ]);
  });

  it("treats empty model text as non-superseding", () => {
    const segs = [
      { kind: "system" as const, text: "正在做事" },
      { kind: "model" as const, text: "   " },
    ];
    const result = dropStaleSysSegments(segs);
    expect(result).toHaveLength(2);
  });
});

describe("splitModelByEnum", () => {
  it("splits on 其一/其二/其三/其四 markers", () => {
    const text = "总览。其一，A 内容。其二，B 内容。其三，C 内容。";
    const parts = splitModelByEnum(text);
    expect(parts.length).toBeGreaterThanOrEqual(3);
    expect(parts[1]).toContain("其一");
    expect(parts[2]).toContain("其二");
  });

  it("splits on 首先/其次/再者/最后", () => {
    const text = "首先，分析问题。其次，给出方案。再者，验证假设。最后，总结。";
    const parts = splitModelByEnum(text);
    expect(parts.length).toBe(4);
  });

  it("splits before 核心挑战 even without enumeration", () => {
    const text = "本研究围绕 X 展开。核心挑战在于 Y 与 Z 的协同。";
    const parts = splitModelByEnum(text);
    expect(parts).toHaveLength(2);
    expect(parts[1].startsWith("核心挑战")).toBe(true);
  });

  it("returns single chunk when no enumeration marker", () => {
    const text = "纯散文式描述，没有任何枚举词。";
    expect(splitModelByEnum(text)).toEqual([text]);
  });

  it("handles empty input", () => {
    expect(splitModelByEnum("")).toEqual([""]);
  });
});
