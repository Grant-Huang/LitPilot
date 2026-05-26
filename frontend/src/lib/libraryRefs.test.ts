import { describe, expect, it } from "vitest";
import { filterLibraryRefs } from "./libraryRefs";
import type { LibraryItem } from "./libraryTypes";

const sample: LibraryItem[] = [
  {
    id: "a1",
    display_index: 1,
    title: "Agentic AI in Manufacturing",
    authors: ["Alice"],
    url: "https://arxiv.org/abs/2301.00001",
    availability: { has_full_text: true, fetch_status: "ok", cite_status: "ok" },
    starred: false,
  },
  {
    id: "a2",
    display_index: 2,
    title: "MES Systems",
    authors: ["Bob"],
    url: "https://example.com/paper",
    availability: { fetch_status: "failed", cite_status: "ok" },
    starred: true,
  },
];

describe("filterLibraryRefs", () => {
  it("空查询返回全部", () => {
    expect(filterLibraryRefs(sample, "")).toHaveLength(2);
  });

  it("按标题或 URL 过滤", () => {
    expect(filterLibraryRefs(sample, "arxiv")).toHaveLength(1);
    expect(filterLibraryRefs(sample, "MES")).toHaveLength(1);
  });

  it("按筛选器过滤", () => {
    expect(filterLibraryRefs(sample, "", "fulltext")).toHaveLength(1);
    expect(filterLibraryRefs(sample, "", "failed")).toHaveLength(1);
    expect(filterLibraryRefs(sample, "", "starred")).toHaveLength(1);
  });
});
