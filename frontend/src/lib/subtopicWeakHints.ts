export type WeakSubtopicHint = {
  passIndex: number;
  title: string;
  hitsTaken: number;
};

type ExtensionRow = { name: string; data: Record<string, unknown> };

function topicTitle(
  passIndex: number,
  data: Record<string, unknown>,
  subTopics?: Array<{ title?: string }>,
): string {
  const fromEvent = String(data.topic_title ?? "").trim();
  if (fromEvent) return fromEvent;
  const fromPlan = subTopics?.[passIndex - 1]?.title?.trim();
  if (fromPlan) return fromPlan;
  return `主题 ${passIndex}`;
}

/** 薄弱阈值：max(3, per_query 的 25%) */
export function weakSubtopicThreshold(perQueryMax: number): number {
  const base = Number.isFinite(perQueryMax) && perQueryMax > 0 ? perQueryMax : 8;
  return Math.max(3, Math.floor(base * 0.25));
}

export function weakSubtopicsFromExtensions(
  extensions: ExtensionRow[],
  subTopics?: Array<{ title?: string }>,
): WeakSubtopicHint[] {
  for (let i = extensions.length - 1; i >= 0; i -= 1) {
    const ext = extensions[i];
    if (ext.name !== "literature_search_merge") continue;
    const raw = ext.data.weak_subtopics;
    if (Array.isArray(raw) && raw.length) {
      return raw
        .map((row) => {
          const r = row as Record<string, unknown>;
          const passIndex =
            typeof r.pass_index === "number" ? r.pass_index : 0;
          const hitsTaken =
            typeof r.hits_taken === "number" ? r.hits_taken : 0;
          const title = String(r.title ?? "").trim() || `主题 ${passIndex}`;
          if (passIndex <= 0) return null;
          return { passIndex, title, hitsTaken };
        })
        .filter((h): h is WeakSubtopicHint => Boolean(h));
    }
    break;
  }

  let perQuery = 8;
  let totalPasses = 0;
  const passHits = new Map<number, { hits: number; title: string }>();

  for (const ext of extensions) {
    if (ext.name === "literature_search_plan") {
      const pq = ext.data.per_query_max_results;
      if (typeof pq === "number") perQuery = pq;
      const queries = ext.data.queries;
      if (Array.isArray(queries)) totalPasses = queries.length;
    }
    if (ext.name === "literature_search_pass_done") {
      const passIndex =
        typeof ext.data.pass_index === "number" ? ext.data.pass_index : 0;
      if (passIndex <= 0) continue;
      const hitsTaken =
        typeof ext.data.hits_taken === "number"
          ? ext.data.hits_taken
          : typeof ext.data.hits === "number"
            ? ext.data.hits
            : 0;
      passHits.set(passIndex, {
        hits: hitsTaken,
        title: topicTitle(passIndex, ext.data, subTopics),
      });
    }
  }

  if (totalPasses < 2 && passHits.size < 2) return [];

  const threshold = weakSubtopicThreshold(perQuery);
  const hints: WeakSubtopicHint[] = [];
  for (const [passIndex, row] of passHits) {
    if (row.hits >= threshold) continue;
    hints.push({
      passIndex,
      title: row.title,
      hitsTaken: row.hits,
    });
  }
  return hints.sort((a, b) => a.passIndex - b.passIndex);
}

export function weakSubtopicsFromTrace(
  trace?: { literatureStats?: Record<string, unknown> },
): WeakSubtopicHint[] {
  const raw = trace?.literatureStats?.weakSubtopics;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((row) => {
      const r = row as Record<string, unknown>;
      const passIndex = typeof r.passIndex === "number" ? r.passIndex : 0;
      const hitsTaken = typeof r.hitsTaken === "number" ? r.hitsTaken : 0;
      const title =
        String(r.title ?? "").trim() || (passIndex ? `主题 ${passIndex}` : "");
      if (!passIndex) return null;
      return { passIndex, title, hitsTaken };
    })
    .filter((h): h is WeakSubtopicHint => Boolean(h));
}

export function formatWeakSubtopicBrief(hints: WeakSubtopicHint[]): string {
  if (!hints.length) return "";
  if (hints.length === 1) {
    const h = hints[0];
    return `「${h.title}」仅纳入 ${h.hitsTaken} 篇，建议 expand_search 或补充检索式。`;
  }
  const preview = hints
    .slice(0, 3)
    .map((h) => `「${h.title}」(${h.hitsTaken} 篇)`)
    .join("、");
  const suffix = hints.length > 3 ? ` 等 ${hints.length} 个方向` : "";
  return `${preview}${suffix} 文献偏少，建议 expand_search。`;
}
