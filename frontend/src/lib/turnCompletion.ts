import type { ExecutionTrace } from "@/lib/executionTrace";
import type { TurnWorkflow, WorkflowCard } from "@/lib/turnWorkflow";
import { humanizeDurationMs } from "@/lib/toolLabels";

export type TurnCompletionStats = {
  searchPasses: number;
  mergedHits: number | null;
  fetchOk: number;
  fetchFailed: number;
  hasReview: boolean;
  hasMatrix: boolean;
  failedLiterature: number;
};

export type TurnCompletionSummary = {
  headline: string;
  stats: TurnCompletionStats;
  brief: string;
};

function countFetchTools(trace: ExecutionTrace | undefined): {
  ok: number;
  failed: number;
} {
  if (!trace) return { ok: 0, failed: 0 };
  let ok = 0;
  let failed = 0;
  for (const t of trace.tools) {
    if (t.name !== "web_fetch") continue;
    if (t.status === "error") failed += 1;
    else if (t.status === "done") ok += 1;
  }
  return { ok, failed };
}

function mergedHitsFromExtensions(
  extensions: Array<{ name: string; data: Record<string, unknown> }>,
): number | null {
  for (let i = extensions.length - 1; i >= 0; i -= 1) {
    const ext = extensions[i];
    if (ext.name !== "literature_search_merge") continue;
    const deduped = ext.data.deduped;
    if (typeof deduped === "number") return deduped;
  }
  return null;
}

function searchPassCount(trace: ExecutionTrace | undefined): number {
  if (!trace) return 0;
  return trace.tools.filter((t) => t.name === "web_search" && t.status === "done")
    .length;
}

export function summarizeWorkflowCard(card: WorkflowCard): string {
  if (card.summary?.trim()) return card.summary.trim();
  const toolDone = card.steps.filter(
    (s) => s.kind === "tool" && s.status === "done",
  ).length;
  const toolErr = card.steps.filter(
    (s) => s.kind === "tool" && s.status === "error",
  ).length;

  if (card.type === "search") {
    const merge = card.steps.find((s) => s.title.includes("去重"));
    if (merge) {
      const m = /去重\s+(\d+)/.exec(merge.title);
      if (m) return `纳入 ${m[1]} 篇`;
    }
    if (toolDone) return `${toolDone} 轮检索`;
  }
  if (card.type === "fetch") {
    if (toolDone || toolErr) {
      return toolErr ? `${toolDone} 篇 · ${toolErr} 失败` : `${toolDone} 篇`;
    }
    const queue = card.steps.find((s) => s.title.includes("抓取队列"));
    if (queue) return queue.title.replace("抓取队列 ", "");
  }
  if (card.type === "generate") return "已完成";
  if (card.type === "brief" && card.body) {
    const first = card.body.split(/\r?\n/).find((l) => l.trim());
    return first ? first.slice(0, 48) : "已完成";
  }
  if (card.type === "understand" && card.subTopics?.length) {
    const titles = card.subTopics
      .map((st) => (st.title ?? "").trim())
      .filter(Boolean);
    if (titles.length) {
      const preview = titles.slice(0, 2).join("、");
      return titles.length > 2 ? `${preview} 等 ${titles.length} 个子主题` : preview;
    }
  }
  if (toolDone) return `${toolDone} 步`;
  return "已完成";
}

export function buildTurnCompletionSummary(
  workflow: TurnWorkflow,
  opts?: {
    trace?: ExecutionTrace;
    extensions?: Array<{ name: string; data: Record<string, unknown> }>;
    hasReview?: boolean;
    hasMatrix?: boolean;
    failedLiterature?: number;
    chatText?: string;
  },
): TurnCompletionSummary {
  const extensions = opts?.extensions ?? [];
  const fetch = countFetchTools(opts?.trace);
  const merged = mergedHitsFromExtensions(extensions);
  const searchPasses = searchPassCount(opts?.trace);
  const hasReview = Boolean(opts?.hasReview);
  const hasMatrix = Boolean(opts?.hasMatrix);
  const failedLiterature = opts?.failedLiterature ?? 0;

  const stats: TurnCompletionStats = {
    searchPasses,
    mergedHits: merged,
    fetchOk: fetch.ok,
    fetchFailed: fetch.failed,
    hasReview,
    hasMatrix,
    failedLiterature,
  };

  const parts: string[] = [];
  if (searchPasses > 0) parts.push(`检索 ${searchPasses} 轮`);
  if (merged != null) parts.push(`纳入 ${merged} 篇`);
  if (fetch.ok > 0) parts.push(`抓取 ${fetch.ok} 篇`);
  if (fetch.failed > 0) parts.push(`${fetch.failed} 篇失败`);
  if (hasReview) parts.push("综述已生成");
  if (hasMatrix) parts.push("矩阵已更新");
  if (failedLiterature > 0) parts.push(`${failedLiterature} 条未纳入`);

  const headline = parts.length ? parts.join(" · ") : workflow.summary || "本回合已完成";

  let brief = "";
  const chat = (opts?.chatText ?? "").trim();
  if (chat && workflow.intent === "query_corpus") {
    brief = chat.slice(0, 400);
  } else if (hasReview) {
    brief =
      merged != null
        ? `综述已写入右侧面板，本次共纳入 ${merged} 篇文献${fetch.failed ? `（${fetch.failed} 篇抓取失败）` : ""}。`
        : "综述已写入右侧面板，可在「综述」Tab 查看与导出。";
  } else if (merged != null) {
    brief = `检索与抓取已完成，共纳入 ${merged} 篇，可继续追问或补充链接。`;
  }

  return { headline, stats, brief };
}

export function enrichWorkflowCardSummaries(cards: WorkflowCard[]): WorkflowCard[] {
  return cards.map((c) => ({
    ...c,
    summary: summarizeWorkflowCard(c),
  }));
}

export function formatStatDuration(totalMs: number | undefined): string | null {
  return humanizeDurationMs(totalMs);
}
