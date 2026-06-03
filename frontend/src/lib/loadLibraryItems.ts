import { libraryApi } from "@/lib/api";
import { normalizeLibraryItem, type LibraryItem } from "@/lib/libraryTypes";

/** Load library items; fall back to legacy refs API when items endpoint fails. */
export async function loadLibraryItems(): Promise<LibraryItem[]> {
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
}
