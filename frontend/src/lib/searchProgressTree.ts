export type SubtopicPhaseStatus = "pending" | "running" | "done" | "error";

export type SubtopicPhaseNode = {
  status: SubtopicPhaseStatus;
  label: string;
  detail?: string;
};

export type SourceNode = {
  label: string;
  hits: number;
  hits_taken: number;
  status: SubtopicPhaseStatus;
  failed?: boolean;
};

export type FilterDetailItem = {
  title: string;
  url?: string;
  keep: boolean;
  score?: number;
  reason?: string;
};

export type SubtopicProgressNode = {
  id: string;
  title: string;
  query: string;
  search: SubtopicPhaseNode;
  filter: SubtopicPhaseNode;
  sources: SourceNode[];
  filterDetails: FilterDetailItem[];
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
      sources: [],
      filterDetails: [],
    };
    map.set(id, node);
  }
  if (title && !node.title) node.title = title;
  if (query && !node.query) node.query = query;
  return node;
}

export function subtopicDone(node: SubtopicProgressNode): boolean {
  return node.search.status === "done" && node.filter.status === "done";
}

/** 已过检索阶段即为"完成检索"：用于 aggregate 计数（不含 filter 状态判断）。 */
function subtopicSearchDone(node: SubtopicProgressNode): boolean {
  return node.search.status === "done";
}

export function buildSearchProgressTree(
  extensions: ExtensionRow[],
  subTopics?: SubtopicPlanRow[],
): SearchProgressSummary {
  const map = new Map<string, SubtopicProgressNode>();
  // Track per-pass source counts for subtopics without explicit subtopic_id
  type PassSourceMap = Map<number, Map<string, SourceNode>>;
  const passSources: PassSourceMap = new Map();

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
    const passIndex = typeof data.pass_index === "number" ? data.pass_index : undefined;

    if (ext.name === "literature_search_source_done") {
      const label = String(data.label ?? data.source ?? "");
      const hits = typeof data.hits === "number" ? data.hits : 0;
      const hitsTaken = typeof data.hits_taken === "number" ? data.hits_taken : 0;
      const failed = Boolean(data.failed);

      if (subtopicId) {
        const node = ensureSubtopic(map, subtopicId);
        node.sources.push({
          label,
          hits,
          hits_taken: hitsTaken,
          status: failed ? "error" : "done",
          failed,
        });
      } else if (passIndex != null) {
        // Fallback: track by pass index
        if (!passSources.has(passIndex)) passSources.set(passIndex, new Map());
        const srcMap = passSources.get(passIndex)!;
        srcMap.set(label, { label, hits, hits_taken: hitsTaken, status: failed ? "error" : "done", failed });
      }
      continue;
    }

    if (!subtopicId) continue;

    const node = ensureSubtopic(
      map,
      subtopicId,
      String(data.title ?? ""),
      "",
    );

    if (ext.name === "literature_subtopic_search_done") {
      const raw = typeof data.raw_count === "number" ? data.raw_count : 0;
      node.search = phase("done", "检索", "命中 " + raw + " 篇");
      node.filter = phase("running", "过滤");
      if (typeof data.duration_ms === "number") node.durationMs = data.duration_ms;
      continue;
    }

    if (ext.name === "literature_subtopic_filter_done") {
      const kept =
        typeof data.kept_count === "number" ? data.kept_count : 0;
      node.filter = phase("done", "过滤", "保留 " + kept + " 篇");

      // Parse kept items
      const keptItems = Array.isArray(data.kept) ? data.kept : [];
      for (const item of keptItems as Array<Record<string, unknown>>) {
        node.filterDetails.push({
          title: String(item.title ?? ""),
          url: String(item.url ?? ""),
          keep: true,
        });
      }

      // Parse rejected items
      const rejectedItems = Array.isArray(data.rejected) ? data.rejected : [];
      for (const item of rejectedItems as Array<Record<string, unknown>>) {
        node.filterDetails.push({
          title: String(item.title ?? ""),
          url: String(item.url ?? ""),
          keep: false,
          score: typeof item.score === "number" ? item.score : undefined,
          reason: String(item.reason ?? ""),
        });
      }
      continue;
    }
  }

  const subtopics = [...map.values()];

  // Merge pass-level source data into subtopics if they have no sources yet
  if (passSources.size > 0 && subtopics.length > 0) {
    for (const node of subtopics) {
      if (node.sources.length > 0) continue;
      // Assign first pass's source data to any substopic missing sources
      for (const [, srcMap] of passSources) {
        for (const [, src] of srcMap) {
          node.sources.push(src);
        }
      }
      break;
    }
  }

  const totalSubtopics = subtopics.length;
  const completedSubtopics = subtopics.filter(subtopicSearchDone).length;
  const allDone = totalSubtopics > 0 && subtopics.filter(subtopicDone).length >= totalSubtopics;

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
  return "主题 " + (topic.passIndex ?? "");
}

export function subtopicDisplayTitle(node: SubtopicProgressNode): string {
  return node.title.trim() || node.query.slice(0, 72) || node.id;
}

export function subtopicStatusLabel(node: SubtopicProgressNode): string {
  if (subtopicDone(node)) {
    const filterDetail = node.filter.detail ?? "";
    return filterDetail ? "完成 · " + filterDetail : "完成";
  }
  if (node.filter.status === "running") return "过滤中…";
  if (node.search.status === "running") return "检索中…";
  return "待开始";
}
