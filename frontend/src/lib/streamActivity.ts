import type { StreamState } from "@meso.ai/ui";

export const STREAM_SILENCE_WARN_SEC = 5;
export const STREAM_SILENCE_SLOW_SEC = 20;

export type StreamActivityLevel = "active" | "waiting" | "slow";

export type StreamParallelismInfo = {
  searchLabel: string | null;
  fetchParallel: number | null;
};

export type StreamProgressSnapshot = {
  stage: string;
  detail: string;
  elapsedMs: number;
  passIndex?: number;
  passTotal?: number;
  completed?: number;
  total?: number;
};

export type StreamActivitySnapshot = {
  stage: string;
  detail: string;
  elapsedSec: number;
  silenceSec: number;
  level: StreamActivityLevel;
  progress?: StreamProgressSnapshot;
  parallelism: StreamParallelismInfo;
};

const STAGE_LABELS: Record<string, string> = {
  search: "文献检索",
  fetch: "抓取全文",
  cite: "引用抽取",
  generate: "综述生成",
  understand: "理解研究问题",
  brief: "研究计划",
};

function latestSearchDetail(
  log: StreamState["extensionLog"],
): string {
  for (let i = log.length - 1; i >= 0; i -= 1) {
    const ext = log[i];
    const name = ext.payload.name;
    const data = (ext.payload.data ?? {}) as Record<string, unknown>;
    if (name === "literature_search_source_start") {
      const label = String(data.label ?? data.source ?? "检索源");
      const topic = String(data.topic_title ?? "").trim();
      return topic ? `${topic} · ${label}` : label;
    }
    if (name === "literature_search_pass_start") {
      const topic = String(data.topic_title ?? "").trim();
      if (topic) return topic;
      const q = String(data.query ?? "").trim();
      if (q) return q.slice(0, 72);
    }
  }
  return "";
}

export function extractStreamParallelism(
  log: StreamState["extensionLog"],
): StreamParallelismInfo {
  let searchLabel: string | null = null;
  let fetchParallel: number | null = null;
  let maxInflight = 0;

  for (const ext of log) {
    const name = ext.payload.name;
    const data = (ext.payload.data ?? {}) as Record<string, unknown>;
    if (name === "literature_search_plan") {
      const mode = String(data.parallel_mode ?? "");
      if (mode === "by_source") {
        const n =
          typeof data.source_parallel === "number" ? data.source_parallel : 5;
        searchLabel = `并行检索 ${n} 个数据源`;
      } else if (mode === "by_topic") {
        const n =
          typeof data.topic_parallel === "number"
            ? data.topic_parallel
            : typeof data.search_parallel === "number"
              ? data.search_parallel
              : 1;
        if (n > 1) searchLabel = `并行检索 ${n} 个子主题`;
      }
    }
    if (name === "literature_progress" && data.stage === "fetch") {
      if (typeof data.parallel === "number") {
        fetchParallel = Math.max(fetchParallel ?? 0, data.parallel);
      }
      if (typeof data.in_flight === "number") {
        maxInflight = Math.max(maxInflight, data.in_flight);
      }
    }
  }

  if (!fetchParallel && maxInflight > 1) {
    fetchParallel = maxInflight;
  }

  return { searchLabel, fetchParallel };
}

export function formatParallelismChips(
  info: StreamParallelismInfo,
): string[] {
  const chips: string[] = [];
  if (info.searchLabel) chips.push(info.searchLabel);
  if (info.fetchParallel != null && info.fetchParallel > 1) {
    chips.push(`同时抓取 ${info.fetchParallel} 篇`);
  }
  return chips;
}

function latestProgress(
  log: StreamState["extensionLog"],
): StreamProgressSnapshot | undefined {
  for (let i = log.length - 1; i >= 0; i -= 1) {
    const ext = log[i];
    if (ext.payload.name !== "literature_progress") continue;
    const data = (ext.payload.data ?? {}) as Record<string, unknown>;
    const stage = typeof data.stage === "string" ? data.stage : "";
    if (!stage) continue;
    return {
      stage,
      detail: typeof data.detail === "string" ? data.detail : "",
      elapsedMs:
        typeof data.elapsed_ms === "number" ? Math.floor(data.elapsed_ms) : 0,
      passIndex:
        typeof data.pass_index === "number" ? data.pass_index : undefined,
      passTotal:
        typeof data.pass_total === "number" ? data.pass_total : undefined,
      completed:
        typeof data.completed === "number" ? data.completed : undefined,
      total: typeof data.total === "number" ? data.total : undefined,
    };
  }
  return undefined;
}

function activeStageName(stream: StreamState): string {
  for (let i = stream.stages.length - 1; i >= 0; i -= 1) {
    if (stream.stages[i].state === "active") return stream.stages[i].name;
  }
  const progress = latestProgress(stream.extensionLog);
  if (progress) {
    return STAGE_LABELS[progress.stage] ?? progress.stage;
  }
  return "处理中";
}

function runningToolHint(stream: StreamState): string {
  for (const id of stream.toolCallOrder) {
    const tc = stream.toolCalls[id];
    if (tc?.status === "running" || tc?.status === "pending") {
      const q = String((tc.call.args as Record<string, unknown>)?.query ?? "").trim();
      if (q) return q.slice(0, 72);
      const url = String((tc.call.args as Record<string, unknown>)?.url ?? "").trim();
      if (url) {
        try {
          return new URL(url).hostname;
        } catch {
          return url.slice(0, 48);
        }
      }
      return tc.call.name.replace(/_/g, " ");
    }
  }
  return "";
}

export function buildStreamActivitySnapshot(
  stream: StreamState,
  nowMs: number,
  lastEventAtMs: number,
  streamStartedAtMs: number,
): StreamActivitySnapshot {
  const silenceSec = Math.max(0, Math.floor((nowMs - lastEventAtMs) / 1000));
  const elapsedSec = Math.max(0, Math.floor((nowMs - streamStartedAtMs) / 1000));
  const progress = latestProgress(stream.extensionLog);
  const searchDetail = latestSearchDetail(stream.extensionLog);
  const stage = progress
    ? STAGE_LABELS[progress.stage] ?? progress.stage
    : activeStageName(stream);
  const toolHint = runningToolHint(stream);
  const detail =
    searchDetail ||
    progress?.detail?.trim() ||
    toolHint ||
    (stream.thinkContent ? "思考中…" : "");

  let level: StreamActivityLevel = "active";
  if (silenceSec >= STREAM_SILENCE_SLOW_SEC) level = "slow";
  else if (silenceSec >= STREAM_SILENCE_WARN_SEC) level = "waiting";

  return {
    stage,
    detail,
    elapsedSec,
    silenceSec,
    level,
    progress,
    parallelism: extractStreamParallelism(stream.extensionLog),
  };
}

export function formatStreamActivityHint(snapshot: StreamActivitySnapshot): string {
  const parts: string[] = [snapshot.stage];
  if (snapshot.progress?.passIndex && snapshot.progress.passTotal) {
    parts.push(`第 ${snapshot.progress.passIndex}/${snapshot.progress.passTotal} 轮`);
  }
  if (
    snapshot.progress?.completed != null &&
    snapshot.progress.total != null &&
    snapshot.progress.total > 0
  ) {
    parts.push(`${snapshot.progress.completed}/${snapshot.progress.total}`);
  }
  if (snapshot.level === "waiting" || snapshot.level === "slow") {
    parts.push(`等待中 ${snapshot.silenceSec}s`);
  } else if (snapshot.elapsedSec > 0) {
    parts.push(`${snapshot.elapsedSec}s`);
  }
  return parts.join(" · ");
}

export function streamActivityFingerprint(stream: StreamState): string {
  const extLen = stream.extensionLog.length;
  const toolLen = stream.toolCallOrder.length;
  const stageLen = stream.stages.length;
  const thinkLen = stream.thinkContent?.length ?? 0;
  const textLen = stream.textContent?.length ?? 0;
  const wfLen = stream.workflowRunOrder.length;
  const lastTool = stream.toolCallOrder[toolLen - 1] ?? "";
  const lastStage = stream.stages[stageLen - 1]?.name ?? "";
  return `${extLen}|${toolLen}|${lastTool}|${stageLen}|${lastStage}|${thinkLen}|${textLen}|${wfLen}|${stream.status}`;
}
