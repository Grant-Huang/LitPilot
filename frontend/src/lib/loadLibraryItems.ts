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
      } catch {
        try {
          const legacy = await libraryApi.refs();
          const raw =
            (legacy.items as Record<string, unknown>[]) ||
            (legacy.index?.refs as Record<string, unknown>[]) ||
            [];
          return raw.map((r) => normalizeLibraryItem(r));
        } catch {
          return [];
        }
      }
    },
    ttlMs,
  );
}
