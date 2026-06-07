export type SubtopicPhaseStatus = "pending" | "running" | "done" | "error";

export type SubtopicPhaseNode = {
  status: SubtopicPhaseStatus;
  label: string;
  detail?: string;
};

export type SubtopicProgressNode = {
  id: string;
  title: string;
  query: string;
  search: SubtopicPhaseNode;
  filter: SubtopicPhaseNode;
  fetch: SubtopicPhaseNode;
  durationMs?: number;
};

export type SearchProgressSummary = {
  subtopics: SubtopicProgressNode[];
  completedSubtopics: number;
  totalSubtopics: number;
  allDone: boolean;
};

type ExtensionRow = { name: string; data: Record<string, unknown> };

type SubtopicPlanRow = { id: string; title: string; search_query: string };

function phase(
  status: SubtopicPhaseStatus,
  label: string,
  detail?: string,
): SubtopicPhaseNode {
  return { status, label, detail };
}

function ensureSubtopic(
  map: Map<string, SubtopicProgressNode>,
  id: string,
  title = "",
  query = "",
): SubtopicProgressNode {
  let node = map.get(id);
  if (!node) {
    node = {
      id,
      title,
      query,
      search: phase("pending", "检索"),
      filter: phase("pending", "过滤"),
      fetch: phase("pending", "抓取"),
    };
    map.set(id, node);
  }
  if (title && !node.title) node.title = title;
  if (query && !node.query) node.query = query;
  return node;
}

function subtopicDone(node: SubtopicProgressNode): boolean {
  return (
    node.search.status === "done" &&
    node.filter.status === "done" &&
    node.fetch.status === "done"
  );
}

export function buildSearchProgressTree(
  extensions: ExtensionRow[],
  subTopics?: SubtopicPlanRow[],
): SearchProgressSummary {
  const map = new Map<string, SubtopicProgressNode>();

  if (subTopics?.length) {
    for (const st of subTopics) {
      ensureSubtopic(map, st.id, st.title, st.search_query);
    }
  }

  for (const ext of extensions) {
    const data = ext.data ?? {};

    if (ext.name === "literature_subtopic_plan") {
      const rows = data.subtopics;
      if (Array.isArray(rows)) {
        for (const row of rows) {
          const r = row as Record<string, unknown>;
          const id = String(r.id ?? "").trim();
          if (!id) continue;
          ensureSubtopic(
            map,
            id,
            String(r.title ?? ""),
            String(r.search_query ?? ""),
          );
        }
      }
      continue;
    }

    const subtopicId = String(data.subtopic_id ?? "").trim();
    if (!subtopicId) continue;

    const node = ensureSubtopic(
      map,
      subtopicId,
      String(data.title ?? ""),
      "",
    );

    if (ext.name === "literature_subtopic_search_done") {
      const raw = typeof data.raw_count === "number" ? data.raw_count : 0;
      node.search = phase("done", "检索", `命中 ${raw} 篇`);
      node.filter = phase("running", "过滤");
      if (typeof data.duration_ms === "number") node.durationMs = data.duration_ms;
      continue;
    }

    if (ext.name === "literature_subtopic_filter_done") {
      const kept =
        typeof data.kept_count === "number" ? data.kept_count : 0;
      node.filter = phase("done", "过滤", `保留 ${kept} 篇`);
      node.fetch = phase("running", "抓取");
      continue;
    }

    if (ext.name === "literature_subtopic_fetch_done") {
      const ok = typeof data.ok === "number" ? data.ok : 0;
      const failed = typeof data.failed === "number" ? data.failed : 0;
      const skipped = typeof data.skipped === "number" ? data.skipped : 0;
      const parts = [`成功 ${ok}`];
      if (failed) parts.push(`失败 ${failed}`);
      if (skipped) parts.push(`跳过 ${skipped}`);
      node.fetch = phase(
        failed && !ok ? "error" : "done",
        "抓取",
        parts.join(" · "),
      );
    }
  }

  const subtopics = [...map.values()];
  const totalSubtopics = subtopics.length;
  const completedSubtopics = subtopics.filter(subtopicDone).length;
  const allDone = totalSubtopics > 0 && completedSubtopics >= totalSubtopics;

  return {
    subtopics,
    completedSubtopics,
    totalSubtopics,
    allDone,
  };
}

/** @deprecated v2 使用 subtopicDisplayTitle */
export function topicDisplayTitle(topic: {
  topicTitle?: string;
  title?: string;
  query?: string;
  passIndex?: number;
}): string {
  const title = String(topic.topicTitle ?? topic.title ?? "").trim();
  if (title) return title;
  const query = String(topic.query ?? "").trim();
  if (query) return query.slice(0, 72);
  return `主题 ${topic.passIndex ?? ""}`.trim();
}

export function subtopicDisplayTitle(node: SubtopicProgressNode): string {
  return node.title.trim() || node.query.slice(0, 72) || node.id;
}

export function subtopicStatusLabel(node: SubtopicProgressNode): string {
  if (subtopicDone(node)) {
    const fetchDetail = node.fetch.detail ?? "";
    return fetchDetail ? `完成 · ${fetchDetail}` : "完成";
  }
  if (node.fetch.status === "running") return "抓取中…";
  if (node.filter.status === "running") return "过滤中…";
  if (node.search.status === "running") return "检索中…";
  return "待开始";
}

/** 兼容旧测试/组件：映射到 subtopic 状态 */
export function topicStatusLabel(topic: {
  status?: string;
  hitsTaken?: number;
  hitsFound?: number;
  hits?: number;
  sourcesDone?: number;
  sourceTotal?: number;
}): string {
  if (topic.status === "done") {
    const taken = topic.hitsTaken ?? topic.hits ?? 0;
    const found = topic.hitsFound ?? taken;
    if (taken > 0 || found > 0) {
      return `检索完成 · 搜到 ${found} 篇，取 ${taken} 篇`;
    }
    return "检索完成";
  }
  if (topic.status === "running") {
    return `检索中 · ${topic.sourcesDone ?? 0}/${topic.sourceTotal ?? 5} 源`;
  }
  return "待检索";
}

export function sourceStatusLabel(source: {
  status?: string;
  failed?: boolean;
  hitsFound?: number;
  hitsTaken?: number;
}): string {
  if (source.status === "error" || source.failed) {
    return "检索超时/失败（0）";
  }
  if (source.status === "done") {
    return `检索完成 · 搜到 ${source.hitsFound ?? 0} 篇，取 ${source.hitsTaken ?? 0} 篇`;
  }
  if (source.status === "running") return "检索中…";
  return "待检索";
}
