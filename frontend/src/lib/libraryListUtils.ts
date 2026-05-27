import type { LibraryItem } from "@/lib/libraryTypes";
import { filterLibraryRefs } from "@/lib/libraryRefs";
import { itemMatchesTagFilter } from "@/lib/libraryTags";

export type LibraryListFilter =
  | "all"
  | "fulltext"
  | "failed"
  | "starred"
  | "session";

export type LibraryListDensity = "compact" | "comfortable";

export function itemInSession(item: LibraryItem, sessionId: string): boolean {
  if (!sessionId) return true;
  return (item.provenance || []).some((p) => p.session_id === sessionId);
}

export function isFailedItem(item: LibraryItem): boolean {
  const av = item.availability || {};
  return av.fetch_status === "failed" || av.cite_status === "failed";
}

/** 失败项置顶，其余按 display_index */
export function sortLibraryItems(items: LibraryItem[]): LibraryItem[] {
  return [...items].sort((a, b) => {
    const af = isFailedItem(a) ? 0 : 1;
    const bf = isFailedItem(b) ? 0 : 1;
    if (af !== bf) return af - bf;
    return (a.display_index || 0) - (b.display_index || 0);
  });
}

export function prepareLibraryList(
  items: LibraryItem[],
  options: {
    query?: string;
    filter?: LibraryListFilter;
    sessionId?: string;
    tagFilters?: string[];
    groupFailedFirst?: boolean;
  },
): LibraryItem[] {
  let list = items;
  const tagFilters = options.tagFilters || [];
  if (tagFilters.length) {
    list = list.filter((i) => itemMatchesTagFilter(i, tagFilters));
  }
  if (options.filter === "session" && options.sessionId) {
    list = list.filter((i) => itemInSession(i, options.sessionId!));
  } else if (options.filter && options.filter !== "session") {
    list = filterLibraryRefs(list, "", options.filter);
  }
  const q = (options.query || "").trim();
  if (q) {
    list = filterLibraryRefs(list, q, "all");
  }
  if (options.groupFailedFirst !== false) {
    list = sortLibraryItems(list);
  }
  return list;
}

export function provenanceLabel(count: number): string {
  if (count <= 0) return "";
  return count === 1 ? "1 个综述" : `${count} 个综述`;
}
