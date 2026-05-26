import { describe, expect, it } from "vitest";
import { collapseReviewReferences } from "./reviewDisplay";

describe("collapseReviewReferences", () => {
  it("压缩参考文献章节正文", () => {
    const md = `# Title

## References

[1] Author (2024). Paper.

## Appendix

More`;
    const out = collapseReviewReferences(md);
    expect(out).toContain("文献");
    expect(out).not.toContain("[1] Author (2024)");
    expect(out).toContain("## Appendix");
  });
});
