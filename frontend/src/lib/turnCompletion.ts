import type { ExecutionTrace } from "@/lib/executionTrace";
import {
  formatWeakSubtopicBrief,
  weakSubtopicsFromExtensions,
  weakSubtopicsFromTrace,
} from "@/lib/subtopicWeakHints";
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

function mergedHitsFromTrace(trace: ExecutionTrace | undefined): number | null {
  const merged = trace?.literatureStats?.searchMerged;
  return typeof merged === "number" ? merged : null;
}

function mergedHitsFromWorkflow(workflow: TurnWorkflow): number | null {
  for (const card of workflow.cards) {
    if (card.type !== "search") continue;
    if (card.summary?.trim()) {
      const fromSummary = /纳入\s+(\d+)\s+篇/.exec(card.summary);
      if (fromSummary) return parseInt(fromSummary[1], 10);
    }
    for (const step of card.steps) {
      const fromStep = /去重\s+(\d+)/.exec(step.title);
      if (fromStep) return parseInt(fromStep[1], 10);
    }
  }
  return null;
}

function mergedHitsFromExtensions(
  extensions: Array<{ name: string; data: Record<string, unknown> }>,
): number | null {
  let total = 0;
  let seen = false;
  for (const ext of extensions) {
    if (ext.name !== "literature_subtopic_filter_done") continue;
    const kept = ext.data.kept_count;
    if (typeof kept === "number") {
      total += kept;
      seen = true;
    }
  }
  return seen ? total : null;
}

function searchPassCount(trace: ExecutionTrace | undefined): number {
  if (!trace) return 0;
  return trace.tools.filter((t) => t.name === "web_search" && t.status === "done")
    .length;
}

export type SummarizeCardContext = {
  trace?: ExecutionTrace;
  extensions?: Array<{ name: string; data: Record<string, unknown> }>;
};

function relevanceHintFromExtensions(
  _extensions: Array<{ name: string; data: Record<string, unknown> }>,
): string | null {
  return null;
}

export function summarizeWorkflowCard(
  card: WorkflowCard,
  ctx?: SummarizeCardContext,
): string {
  // pending / running 卡片不显示 summary：避免出现 "抓取全文 4 篇" 配 ○ 待开始
  // 这种"数字摆在 pending 状态旁边"的矛盾视觉（round 3 审查 #E）。
  if (card.state === "pending") return "";
  if (card.summary?.trim()) return card.summary.trim();
  if (card.state === "error") return "失败";
  const toolDone = card.steps.filter(
    (s) => s.kind === "tool" && s.status === "done",
  ).length;
  const toolErr = card.steps.filter(
    (s) => s.kind === "tool" && s.status === "error",
  ).length;
  const merged =
    ctx?.extensions != null
      ? mergedHitsFromExtensions(ctx.extensions)
      : null;
  const fetchCounts = countFetchTools(ctx?.trace);

  if (card.type === "search") {
    if (merged != null) return `纳入 ${merged} 篇`;
    const merge = card.steps.find((s) => s.title.includes("去重"));
    if (merge) {
      const m = /去重\s+(\d+)/.exec(merge.title);
      if (m) return `纳入 ${m[1]} 篇`;
    }
    const passes = searchPassCount(ctx?.trace);
    if (passes > 0) return `${passes} 轮检索`;
    if (toolDone) return `${toolDone} 轮检索`;
  }
  if (card.type === "fetch") {
    if (fetchCounts.ok > 0 || fetchCounts.failed > 0) {
      return fetchCounts.failed
        ? `${fetchCounts.ok} 篇 · ${fetchCounts.failed} 失败`
        : `${fetchCounts.ok} 篇`;
    }
    if (toolDone || toolErr) {
      return toolErr ? `${toolDone} 篇 · ${toolErr} 失败` : `${toolDone} 篇`;
    }
    const queue = card.steps.find((s) => s.title.includes("抓取队列"));
    if (queue) {
      const detail = queue.title.replace(/^抓取队列\s*/, "").trim();
      if (detail) return detail;
    }
  }
  if (card.type === "generate") {
    const hasMatrix = ctx?.trace?.stages.some((s) => s.name.includes("矩阵"));
    return hasMatrix ? "矩阵已生成" : "综述已生成";
  }
  if (card.type === "matrix") return "矩阵已生成";
  if (card.type === "brief" && card.body) {
    // 用 "N RQ · M 关键词" 紧凑摘要替代截断的 "RQ：xxx…"（round 3 审查 #D）。
    // 完整 RQ + 关键词列表展开后在 body 里看。
    const rqMatch = /RQ：([^\n]+)/.exec(card.body);
    const kwMatch = /关键词：([^\n]+)/.exec(card.body);
    const rqCount = rqMatch
      ? rqMatch[1].split(/；|;/).filter((s) => s.trim()).length
      : 0;
    const kwCount = kwMatch
      ? kwMatch[1].split(/、|,/).filter((s) => s.trim()).length
      : 0;
    const parts: string[] = [];
    if (rqCount) parts.push(`${rqCount} RQ`);
    if (kwCount) parts.push(`${kwCount} 关键词`);
    if (parts.length) return parts.join(" · ");
    const first = card.body.split(/\r?\n/).find((l) => l.trim());
    return first ? first.slice(0, 48) : "已完成";
  }
  if (card.type === "understand" && card.subTopics?.length) {
    const n = card.subTopics.length;
    return `${n} 个子主题`;
  }
  if (card.type === "brief" && card.subTopics?.length) {
    return `${card.subTopics.length} 个子主题`;
  }
  if (toolDone) return `${toolDone} 步`;
  if (card.state === "running") return "";
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
    streaming?: boolean;
  },
): TurnCompletionSummary {
  const extensions = opts?.extensions ?? [];
  const fetch = countFetchTools(opts?.trace);
  const merged =
    mergedHitsFromExtensions(extensions) ??
    mergedHitsFromTrace(opts?.trace) ??
    mergedHitsFromWorkflow(workflow);
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

  if (opts?.streaming) {
    const running = workflow.cards.find((c) => c.state === "running");
    const headline = running
      ? `当前：${running.title}`
      : workflow.summary || "处理中…";
    return { headline, stats, brief: "" };
  }

  const parts: string[] = [];
  // 本回合工具总耗时（round 3 审查 #I）。后端尚未发 turn_start/turn_end timestamp，
  // 这里用 sum(tool.duration_ms) 作为近似——会低估纯 LLM 推理时间，但对"有多少
  // 计算量"有直觉指示。后端补齐之后改用真实 turn 耗时。
  const toolElapsedMs = (opts?.trace?.tools ?? []).reduce(
    (acc, t) => acc + (t.duration_ms ?? 0),
    0,
  );
  const elapsed = humanizeDurationMs(toolElapsedMs);
  if (elapsed && toolElapsedMs >= 1000) parts.push(`耗时 ${elapsed}`);
  if (searchPasses > 0) parts.push(`检索 ${searchPasses} 轮`);
  if (merged != null) parts.push(`纳入 ${merged} 篇`);
  if (fetch.ok > 0) parts.push(`抓取 ${fetch.ok} 篇`);
  if (fetch.failed > 0) parts.push(`${fetch.failed} 篇失败`);
  if (hasReview) parts.push("综述已生成");
  if (hasMatrix) parts.push("矩阵已更新");
  if (failedLiterature > 0) parts.push(`${failedLiterature} 条未纳入`);

  const rawSummary = workflow.summary ?? "";
  const fallbackSummary =
    !rawSummary || rawSummary.split(" · ").every((s) => s === "已完成")
      ? ""
      : rawSummary.replace(/(\s*·\s*)+$/, "").trim();
  const headline = parts.length ? parts.join(" · ") : fallbackSummary || "本回合已完成";

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

  const relevanceHint = relevanceHintFromExtensions(extensions);
  if (relevanceHint && !brief.includes(relevanceHint)) {
    brief = brief ? `${brief} ${relevanceHint}` : relevanceHint;
  }

  const planSubTopics = workflow.cards.flatMap((c) => c.subTopics ?? []);
  for (const ext of extensions) {
    if (ext.name !== "literature_subtopic_plan") continue;
    const raw = ext.data.subtopics ?? ext.data.sub_topics;
    if (!Array.isArray(raw)) continue;
    for (const row of raw) {
      const r = row as Record<string, unknown>;
      planSubTopics.push({
        id: String(r.id ?? ""),
        title: String(r.title ?? ""),
        search_query: String(r.search_query ?? ""),
      });
    }
  }
  let weakHints = weakSubtopicsFromExtensions(extensions, planSubTopics);
  if (!weakHints.length) {
    weakHints = weakSubtopicsFromTrace(opts?.trace);
  }
  const weakBrief = formatWeakSubtopicBrief(weakHints);
  if (weakBrief && !brief.includes(weakBrief)) {
    brief = brief ? `${brief} ${weakBrief}` : weakBrief;
  }

  return { headline, stats, brief };
}

export function enrichWorkflowCardSummaries(
  cards: WorkflowCard[],
  ctx?: SummarizeCardContext,
): WorkflowCard[] {
  return cards.map((c) => ({
    ...c,
    summary: summarizeWorkflowCard(c, ctx),
  }));
}

export function formatStatDuration(totalMs: number | undefined): string | null {
  return humanizeDurationMs(totalMs);
}
