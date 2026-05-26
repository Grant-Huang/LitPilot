import type { LibraryItem } from "@/lib/libraryTypes";

export type LibraryRefItem = LibraryItem;

/** 文献库引用列表搜索（标题 / 作者 / URL / DOI / 引用文本） */
export function filterLibraryRefs(
  refs: LibraryItem[],
  query: string,
  filter?: "all" | "fulltext" | "failed" | "starred",
): LibraryItem[] {
  let list = refs;
  if (filter === "fulltext") {
    list = list.filter((i) => i.availability?.has_full_text);
  } else if (filter === "failed") {
    list = list.filter(
      (i) =>
        i.availability?.fetch_status === "failed" ||
        i.availability?.cite_status === "failed",
    );
  } else if (filter === "starred") {
    list = list.filter((i) => i.starred);
  }

  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter((item) => {
    const hay = [
      item.title,
      item.url,
      item.doi,
      item.venue,
      item.year,
      ...(item.authors || []),
      item.citations?.apa,
      String(item.display_index),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}
