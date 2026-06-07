export type SearchHitPreview = {
  url: string;
  title: string;
};

export type SearchSourceNode = {
  source: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  hits: number;
  hitsFound: number;
  hitsTaken: number;
  maxResults: number;
  topUrls: string[];
  topHits: SearchHitPreview[];
  failed: boolean;
  query?: string;
};

export type SearchTopicNode = {
  passIndex: number;
  passTotal: number;
  topicTitle: string;
  query: string;
  status: "pending" | "running" | "done";
  hits: number;
  hitsFound: number;
  hitsTaken: number;
  sourceTotal: number;
  sourcesDone: number;
  sources: SearchSourceNode[];
  durationMs?: number;
};

export type SearchProgressSummary = {
  topics: SearchTopicNode[];
  completedTopics: number;
  totalTopics: number;
  merged: boolean;
  mergedDeduped: number | null;
  allDone: boolean;
};

const SOURCE_ORDER = [
  "openalex",
  "arxiv",
  "crossref",
  "pubmed",
  "semantic_scholar",
];

const SOURCE_LABELS: Record<string, string> = {
  openalex: "OpenAlex",
  arxiv: "arXiv",
  crossref: "CrossRef",
  pubmed: "PubMed",
  semantic_scholar: "Semantic Scholar",
};

function defaultSources(): SearchSourceNode[] {
  return SOURCE_ORDER.map((source) => ({
    source,
    label: SOURCE_LABELS[source] ?? source,
    status: "pending",
    hits: 0,
    hitsFound: 0,
    hitsTaken: 0,
    maxResults: 0,
    topUrls: [],
    topHits: [],
    failed: false,
  }));
}

function topicKey(passIndex: number): string {
  return `pass-${passIndex}`;
}

function ensureTopic(
  map: Map<string, SearchTopicNode>,
  passIndex: number,
  passTotal: number,
  topicTitle = "",
  query = "",
): SearchTopicNode {
  const key = topicKey(passIndex);
  let node = map.get(key);
  if (!node) {
    node = {
      passIndex,
      passTotal,
      topicTitle,
      query,
      status: "pending",
      hits: 0,
      hitsFound: 0,
      hitsTaken: 0,
      sourceTotal: SOURCE_ORDER.length,
      sourcesDone: 0,
      sources: defaultSources(),
    };
    map.set(key, node);
  }
  if (topicTitle && !node.topicTitle) node.topicTitle = topicTitle;
  if (query && !node.query) node.query = query;
  return node;
}

function sourceFor(topic: SearchTopicNode, source: string, label?: string): SearchSourceNode {
  let row = topic.sources.find((s) => s.source === source);
  if (!row) {
    row = {
      source,
      label: label ?? SOURCE_LABELS[source] ?? source,
      status: "pending",
      hits: 0,
      hitsFound: 0,
      hitsTaken: 0,
      maxResults: 0,
      topUrls: [],
      topHits: [],
      failed: false,
    };
    topic.sources.push(row);
  }
  if (label) row.label = label;
  return row;
}


function recountTopic(topic: SearchTopicNode): void {
  topic.sourcesDone = topic.sources.filter(
    (s) => s.status === "done" || s.status === "error",
  ).length;
}

export function buildSearchProgressTree(
  extensions: Array<{ name: string; data: Record<string, unknown> }>,
  subTopics?: Array<{ id?: string; title?: string; search_query?: string }>,
): SearchProgressSummary {
  const map = new Map<string, SearchTopicNode>();
  let merged = false;
  let mergedDeduped: number | null = null;
  let passTotal = 0;

  for (const st of subTopics ?? []) {
    // Pre-seed titles when plan arrives before pass_start
  }
  void subTopics;

  for (const ext of extensions) {
    const data = ext.data;
    const passIndex =
      typeof data.pass_index === "number" ? data.pass_index : 0;
    const passTotalRaw =
      typeof data.pass_total === "number" ? data.pass_total : 0;
    if (passTotalRaw > passTotal) passTotal = passTotalRaw;

    if (ext.name === "literature_search_plan") {
      const queries = data.queries;
      if (Array.isArray(queries)) {
        passTotal = queries.length;
        queries.forEach((q, i) => {
          const title =
            subTopics?.[i]?.title?.trim() ||
            String(q ?? "").slice(0, 48);
          ensureTopic(map, i + 1, passTotal, title, String(q ?? ""));
        });
      }
      continue;
    }

    if (ext.name === "literature_search_pass_start" && passIndex > 0) {
      const title =
        String(data.topic_title ?? "").trim() ||
        subTopics?.[passIndex - 1]?.title?.trim() ||
        "";
      const topic = ensureTopic(
        map,
        passIndex,
        passTotalRaw || passTotal,
        title,
        String(data.query ?? ""),
      );
      topic.status = "running";
      continue;
    }

    if (
      (ext.name === "literature_search_source_start" ||
        ext.name === "literature_search_source_done") &&
      passIndex > 0
    ) {
      const topic = ensureTopic(
        map,
        passIndex,
        passTotalRaw || passTotal,
        String(data.topic_title ?? subTopics?.[passIndex - 1]?.title ?? ""),
        String(data.query ?? ""),
      );
      const src = String(data.source ?? "");
      const row = sourceFor(topic, src, String(data.label ?? ""));
      if (typeof data.max_results === "number") row.maxResults = data.max_results;
      if (typeof data.query === "string") row.query = data.query;
      if (ext.name === "literature_search_source_start") {
        row.status = "running";
      } else {
        row.failed = Boolean(data.failed);
        row.status = row.failed ? "error" : "done";
        const found =
          typeof data.hits_found === "number"
            ? data.hits_found
            : typeof data.hits === "number"
              ? data.hits
              : row.hitsFound;
        const taken =
          typeof data.hits_taken === "number"
            ? data.hits_taken
            : found;
        row.hitsFound = found;
        row.hitsTaken = taken;
        row.hits = found;
        const hitsRaw = data.top_hits;
        if (Array.isArray(hitsRaw)) {
          row.topHits = hitsRaw
            .map((h) => {
              const rowHit = h as Record<string, unknown>;
              const url = String(rowHit.url ?? "").trim();
              const title = String(rowHit.title ?? "").trim();
              if (!url) return null;
              return { url, title: title || url };
            })
            .filter((h): h is SearchHitPreview => Boolean(h));
          row.topUrls = row.topHits.map((h) => h.url);
        } else {
          const urls = data.top_urls;
          if (Array.isArray(urls)) {
            row.topUrls = urls.map((u) => String(u)).filter(Boolean);
            row.topHits = row.topUrls.map((url) => ({ url, title: url }));
          }
        }
      }
      recountTopic(topic);
      continue;
    }

    if (ext.name === "literature_search_pass_done" && passIndex > 0) {
      const topic = ensureTopic(
        map,
        passIndex,
        passTotalRaw || passTotal,
        String(data.topic_title ?? subTopics?.[passIndex - 1]?.title ?? ""),
        String(data.query ?? ""),
      );
      topic.status = "done";
      const taken =
        typeof data.hits_taken === "number"
          ? data.hits_taken
          : typeof data.hits === "number"
            ? data.hits
            : topic.hitsTaken;
      const found =
        typeof data.hits_found === "number" ? data.hits_found : taken;
      topic.hitsTaken = taken;
      topic.hitsFound = found;
      topic.hits = taken;
      if (typeof data.duration_ms === "number") topic.durationMs = data.duration_ms;
      const counts = data.source_counts as Record<string, number> | undefined;
      if (counts) {
        for (const [src, n] of Object.entries(counts)) {
          const row = sourceFor(topic, src);
          if (!row.hitsFound && !row.failed) row.hitsFound = n;
          if (row.status !== "error") row.status = "done";
        }
        recountTopic(topic);
      }
      continue;
    }

    if (ext.name === "literature_search_merge") {
      merged = true;
      if (typeof data.deduped === "number") mergedDeduped = data.deduped;
      for (const topic of map.values()) {
        topic.status = "done";
      }
    }
  }

  const topics = [...map.values()].sort((a, b) => a.passIndex - b.passIndex);
  const totalTopics = passTotal || topics.length;
  const completedTopics = topics.filter((t) => t.status === "done").length;
  const allDone = merged || (totalTopics > 0 && completedTopics >= totalTopics);

  return {
    topics,
    completedTopics,
    totalTopics,
    merged,
    mergedDeduped,
    allDone,
  };
}

export function topicDisplayTitle(topic: SearchTopicNode): string {
  return topic.topicTitle.trim() || topic.query.slice(0, 72) || `主题 ${topic.passIndex}`;
}

export function topicStatusLabel(topic: SearchTopicNode): string {
  const sourcesDone = topic.sourcesDone;
  const sourceTotal = topic.sourceTotal || SOURCE_ORDER.length;
  if (topic.status === "done") {
    const taken = topic.hitsTaken ?? topic.hits;
    const found = topic.hitsFound ?? taken;
    if (taken > 0 || found > 0) {
      return `检索完成 · 搜到 ${found} 篇，取 ${taken} 篇`;
    }
    return "检索完成";
  }
  if (topic.status === "running") {
    return `检索中 · ${sourcesDone}/${sourceTotal} 源`;
  }
  return "待检索";
}

export function sourceStatusLabel(source: SearchSourceNode): string {
  if (source.status === "error" || source.failed) {
    return "检索超时/失败（0）";
  }
  if (source.status === "done") {
    return `检索完成 · 搜到 ${source.hitsFound} 篇，取 ${source.hitsTaken} 篇`;
  }
  if (source.status === "running") {
    return "检索中…";
  }
  return "待检索";
}
