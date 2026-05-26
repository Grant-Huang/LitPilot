import { describe, expect, it } from "vitest";
import { findItemByDisplayIndex } from "./resolveLibraryItem";
import type { LibraryItem } from "./libraryTypes";

describe("findItemByDisplayIndex", () => {
  it("按 display_index 查找", () => {
    const items: LibraryItem[] = [
      {
        id: "x",
        display_index: 3,
        title: "T",
        authors: [],
        url: "https://a",
        availability: {},
      },
    ];
    expect(findItemByDisplayIndex(items, 3)?.id).toBe("x");
    expect(findItemByDisplayIndex(items, 1)).toBeUndefined();
  });
});
