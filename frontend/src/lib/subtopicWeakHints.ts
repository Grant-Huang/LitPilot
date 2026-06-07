export type WeakSubtopicHint = {
  subtopicId: string;
  title: string;
  keptCount: number;
};

type ExtensionRow = { name: string; data: Record<string, unknown> };

/** 薄弱阈值：保留篇数 < 3 视为偏少 */
export const WEAK_KEPT_THRESHOLD = 3;

export function weakSubtopicThreshold(_perQueryMax?: number): number {
  return WEAK_KEPT_THRESHOLD;
}

export function weakSubtopicsFromExtensions(
  extensions: ExtensionRow[],
  subTopics?: Array<{ id?: string; title?: string }>,
): WeakSubtopicHint[] {
  const titleById = new Map<string, string>();
  for (const st of subTopics ?? []) {
    const id = String(st.id ?? "").trim();
    if (id) titleById.set(id, String(st.title ?? "").trim());
  }

  const keptById = new Map<string, number>();
  for (const ext of extensions) {
    if (ext.name !== "literature_subtopic_filter_done") continue;
    const id = String(ext.data.subtopic_id ?? "").trim();
    if (!id) continue;
    const kept =
      typeof ext.data.kept_count === "number" ? ext.data.kept_count : 0;
    keptById.set(id, kept);
  }

  if (keptById.size < 2) return [];

  const hints: WeakSubtopicHint[] = [];
  for (const [subtopicId, keptCount] of keptById) {
    if (keptCount >= WEAK_KEPT_THRESHOLD) continue;
    hints.push({
      subtopicId,
      title: titleById.get(subtopicId) || subtopicId,
      keptCount,
    });
  }
  return hints.sort((a, b) => a.title.localeCompare(b.title, "zh"));
}

export function weakSubtopicsFromTrace(
  trace?: { literatureStats?: Record<string, unknown> },
): WeakSubtopicHint[] {
  const raw = trace?.literatureStats?.weakSubtopics;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((row) => {
      const r = row as Record<string, unknown>;
      const subtopicId = String(r.subtopicId ?? r.passIndex ?? "").trim();
      const keptCount =
        typeof r.keptCount === "number"
          ? r.keptCount
          : typeof r.hitsTaken === "number"
            ? r.hitsTaken
            : 0;
      const title = String(r.title ?? "").trim() || subtopicId;
      if (!subtopicId) return null;
      return { subtopicId, title, keptCount };
    })
    .filter((h): h is WeakSubtopicHint => Boolean(h));
}

export function formatWeakSubtopicBrief(hints: WeakSubtopicHint[]): string {
  if (!hints.length) return "";
  if (hints.length === 1) {
    const h = hints[0];
    return `「${h.title}」仅保留 ${h.keptCount} 篇，可明确说明「修改子主题：…」调整检索式。`;
  }
  const preview = hints
    .slice(0, 3)
    .map((h) => `「${h.title}」(${h.keptCount} 篇)`)
    .join("、");
  const suffix = hints.length > 3 ? ` 等 ${hints.length} 个方向` : "";
  return `${preview}${suffix} 文献偏少，可明确说明「增加/修改子主题」以扩展检索。`;
}
