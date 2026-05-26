import type { LibraryItem } from "@/lib/libraryTypes";

/** 按综述中的 [n] 编号解析文献库条目 */
export function findItemByDisplayIndex(
  items: LibraryItem[],
  index: number,
): LibraryItem | undefined {
  return items.find((i) => i.display_index === index);
}
