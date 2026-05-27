import { describe, expect, it } from "vitest";
import type { LibraryItem } from "@/lib/libraryTypes";
import { itemMatchesTagFilter, normalizeTags } from "@/lib/libraryTags";

const item: LibraryItem = {
  id: "1",
  display_index: 1,
  title: "T",
  authors: [],
  url: "https://x",
  availability: {},
  tags: ["精读", "工业软件"],
};

describe("libraryTags", () => {
  it("normalizeTags dedupes", () => {
    expect(normalizeTags(["精读", " 精读 ", "AI"])).toEqual(["精读", "AI"]);
  });

  it("itemMatchesTagFilter uses OR", () => {
    expect(itemMatchesTagFilter(item, [])).toBe(true);
    expect(itemMatchesTagFilter(item, ["精读"])).toBe(true);
    expect(itemMatchesTagFilter(item, ["不存在"])).toBe(false);
    expect(itemMatchesTagFilter(item, ["不存在", "精读"])).toBe(true);
  });
});
