import { libraryApi } from "@/lib/api";
import { normalizeLibraryItem, type LibraryItem } from "@/lib/libraryTypes";
import { getCachedResource, invalidateCachedResource } from "@/lib/resourceCache";

export const LIBRARY_ITEMS_CACHE_KEY = "library:items";

/** Load library items; fall back to legacy refs API when items endpoint fails. */
export async function loadLibraryItems(options?: {
  force?: boolean;
  ttlMs?: number;
}): Promise<LibraryItem[]> {
  const ttlMs = options?.ttlMs ?? 30_000;
  if (options?.force) {
    invalidateCachedResource(LIBRARY_ITEMS_CACHE_KEY);
  }
  return getCachedResource(
    LIBRARY_ITEMS_CACHE_KEY,
    async () => {
      try {
        const data = await libraryApi.items();
        return data.items || [];
      } catch (primaryErr) {
        // 关键修复：先回退 legacy refs；若 legacy 也失败，向上抛真实异常，
        // 让调用方区分 "空库" 和 "后端宕机"，避免静默把后端故障展示成空列表。
        try {
          const legacy = await libraryApi.refs();
          const raw =
            (legacy.items as Record<string, unknown>[]) ||
            (legacy.index?.refs as Record<string, unknown>[]) ||
            [];
          return raw.map((r) => normalizeLibraryItem(r));
        } catch {
          throw primaryErr;
        }
      }
    },
    ttlMs,
  );
}
