import { describe, expect, it } from "vitest";
import {
  describeWorkflowKind,
  describeWorkflowStep,
  formatWebFetchPlainText,
  isWebFetchCharOnlyPreview,
  parseWebFetchCharCountFromOutput,
  resolveWebFetchCharCount,
  WEB_FETCH_LABEL,
  WEB_FETCH_PREFIX,
} from "./toolLabels";

describe("web_fetch char count display", () => {
  it("parses char count from legacy output", () => {
    expect(parseWebFetchCharCountFromOutput("已抓取正文（约 1234 字）")).toBe(1234);
  });

  it("prefers args char_count over output", () => {
    expect(
      resolveWebFetchCharCount(
        { url: "https://example.com", char_count: 99 },
        "已抓取正文（约 1234 字）",
      ),
    ).toBe(99);
  });

  it("formats plain text with suffix after [url]", () => {
    expect(
      formatWebFetchPlainText("Paper Title", "https://x.com", 500),
    ).toBe("Paper Title [url]（约 500 字）");
  });

  it("detects char-only preview", () => {
    expect(isWebFetchCharOnlyPreview("已抓取正文（约 42 字）", undefined)).toBe(
      true,
    );
    expect(isWebFetchCharOnlyPreview("其他说明", undefined)).toBe(false);
  });

  it("workflow labels match tool labels", () => {
    expect(describeWorkflowKind("web_fetch")).toBe(WEB_FETCH_LABEL);
    expect(describeWorkflowKind("cite_extract")).toBe("抽取引用元数据");
    const title = describeWorkflowStep({
      name: "web_fetch",
      title: "Paper A",
      url: "https://arxiv.org/abs/1",
    });
    expect(title.startsWith(WEB_FETCH_PREFIX)).toBe(true);
    expect(title.includes("Paper A")).toBe(true);
  });
});
