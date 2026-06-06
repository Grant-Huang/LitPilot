export type SearchSourceNode = {
  source: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  hits: number;
  expected: number;
  topUrls: string[];
  query?: string;
};

export type SearchTopicNode = {
  passIndex: number;
  passTotal: number;
  topicTitle: string;
  query: string;
  status: "pending" | "running" | "done";
  hits: number;
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
    expected: 0,
    topUrls: [],
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
      expected: 0,
      topUrls: [],
    };
    topic.sources.push(row);
  }
  if (label) row.label = label;
  return row;
}

function recountTopic(topic: SearchTopicNode): void {
  topic.sourcesDone = topic.sources.filter((s) => s.status === "done").length;
}

export function buildSearchProgressTree(
  extensions: Array<{ name: string; data: Record<string, unknown> }>,
  subTopics?: Array<{ id?: string; title?: string; search_query?: string }>,
): SearchProgressSummary {
  const map = new Map<string, SearchTopicNode>();
  let merged = false;
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
      if (typeof data.expected === "number") row.expected = data.expected;
      if (typeof data.query === "string") row.query = data.query;
      if (ext.name === "literature_search_source_start") {
        row.status = "running";
      } else {
        row.status = "done";
        row.hits = typeof data.hits === "number" ? data.hits : row.hits;
        const urls = data.top_urls;
        if (Array.isArray(urls)) {
          row.topUrls = urls.map((u) => String(u)).filter(Boolean);
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
      topic.hits = typeof data.hits === "number" ? data.hits : topic.hits;
      if (typeof data.duration_ms === "number") topic.durationMs = data.duration_ms;
      const counts = data.source_counts as Record<string, number> | undefined;
      if (counts) {
        for (const [src, n] of Object.entries(counts)) {
          const row = sourceFor(topic, src);
          row.hits = n;
          row.status = "done";
        }
        recountTopic(topic);
      }
      continue;
    }

    if (ext.name === "literature_search_merge") {
      merged = true;
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
    allDone,
  };
}

export function topicDisplayTitle(topic: SearchTopicNode): string {
  return topic.topicTitle.trim() || topic.query.slice(0, 72) || `主题 ${topic.passIndex}`;
}

export function topicStatusLabel(topic: SearchTopicNode): string {
  const done = topic.sourcesDone;
  const total = topic.sourceTotal || SOURCE_ORDER.length;
  if (topic.status === "done") {
    return `检索完成（${topic.hits}/${total}）`;
  }
  return `检索中（${done}/${total}）`;
}

export function sourceStatusLabel(source: SearchSourceNode): string {
  const exp = source.expected || "?";
  if (source.status === "done") {
    return `检索完成（${source.hits}/${exp}）`;
  }
  if (source.status === "running") {
    return `检索中（${source.hits}/${exp}）`;
  }
  return `待检索（0/${exp}）`;
}
