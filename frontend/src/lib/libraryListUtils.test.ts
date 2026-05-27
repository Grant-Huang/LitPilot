import { describe, expect, it } from "vitest";
import {
  isFailedItem,
  itemInSession,
  prepareLibraryList,
  sortLibraryItems,
} from "./libraryListUtils";
import type { LibraryItem } from "./libraryTypes";

const base = (n: number, failed = false): LibraryItem => ({
  id: `id-${n}`,
  display_index: n,
  title: `T${n}`,
  authors: [],
  url: `https://x/${n}`,
  availability: failed
    ? { fetch_status: "failed", cite_status: "pending" }
    : { fetch_status: "ok", cite_status: "ok" },
});

describe("libraryListUtils", () => {
  it("sortLibraryItems 失败项在前", () => {
    const sorted = sortLibraryItems([base(2), base(1, true), base(3)]);
    expect(sorted[0].display_index).toBe(1);
    expect(isFailedItem(sorted[0])).toBe(true);
  });

  it("prepareLibraryList 按标签 OR 筛选", () => {
    const items: LibraryItem[] = [
      { ...base(1), tags: ["精读"] },
      { ...base(2), tags: ["待读"] },
      { ...base(3), tags: ["精读", "工业"] },
    ];
    const out = prepareLibraryList(items, { tagFilters: ["精读"] });
    expect(out).toHaveLength(2);
    expect(out.map((i) => i.display_index)).toEqual([1, 3]);
  });

  it("itemInSession 按 provenance 过滤", () => {
    const item: LibraryItem = {
      ...base(1),
      provenance: [{ session_id: "s1", role: "cite_extract" }],
    };
    expect(itemInSession(item, "s1")).toBe(true);
    expect(itemInSession(item, "s2")).toBe(false);
  });
});
