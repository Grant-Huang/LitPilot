import type { LibraryItem } from "@/lib/libraryTypes";

export const MAX_TAGS_PER_ITEM = 20;
export const MAX_TAG_LEN = 48;

export function normalizeTag(raw: string): string {
  const s = raw.trim().replace(/\s+/g, " ");
  if (!s) return "";
  return s.length > MAX_TAG_LEN ? s.slice(0, MAX_TAG_LEN).trimEnd() : s;
}

export function normalizeTags(tags: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of tags) {
    const tag = normalizeTag(raw);
    if (!tag) continue;
    const key = tag.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(tag);
    if (out.length >= MAX_TAGS_PER_ITEM) break;
  }
  return out;
}

/** 任一选中标签命中即保留（OR） */
export function itemMatchesTagFilter(item: LibraryItem, activeTags: string[]): boolean {
  if (!activeTags.length) return true;
  const itemTags = new Set((item.tags || []).map((t) => t.toLowerCase()));
  return activeTags.some((t) => itemTags.has(t.toLowerCase()));
}
