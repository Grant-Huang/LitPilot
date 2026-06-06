import type { StreamState } from "@meso.ai/ui";
import {
  collectExecutionTraceFromStream,
  type ExecutionTrace,
  type ProcessLine,
  buildProcessLines,
} from "@/lib/executionTrace";
import { enrichWorkflowCardSummaries } from "@/lib/turnCompletion";
import { formatLiteratureIntentLabel } from "@/lib/literatureIntent";

export type WorkflowCardType =
  | "understand"
  | "brief"
  | "search"
  | "fetch"
  | "cite"
  | "attributes"
  | "outline"
  | "generate"
  | "matrix"
  | "revise"
  | "corpus_qa"
  | "clarify"
  | "manage";

export type WorkflowStep = {
  key: string;
  kind: "tool" | "inline" | "think";
  title: string;
  status: "pending" | "running" | "done" | "error";
  preview?: string;
  detail?: string;
  duration_ms?: number;
};

export type WorkflowCard = {
  id: string;
  type: WorkflowCardType;
  title: string;
  state: "pending" | "running" | "done" | "error";
  summary?: string;
  steps: WorkflowStep[];
  body?: string;
  locked?: boolean;
};

export type TurnWorkflow = {
  turnIndex: number;
  intent: string;
  summary: string;
  cards: WorkflowCard[];
  clarifying: boolean;
};

const CARD_TITLES: Record<WorkflowCardType, string> = {
  understand: "理解研究问题",
  brief: "Brief 评估",
  search: "文献检索",
  fetch: "抓取全文",
  cite: "引用抽取",
  attributes: "文献结构化",
  outline: "大纲规划",
  generate: "综述生成",
  matrix: "文献矩阵",
  revise: "章节修订",
  corpus_qa: "语料问答",
  clarify: "等待澄清",
  manage: "文献库操作",
};

function stageToCardType(name: string): WorkflowCardType | null {
  const n = name.trim();
  if (!n || n === "完成" || n === "继续撰写") return null;
  if (n.includes("理解")) return "understand";
  if (n.includes("澄清") || n.includes("等待")) return "clarify";
  if (n.includes("检索")) return "search";
  if (n.includes("抓取")) return "fetch";
  if (n.includes("引用")) return "cite";
  if (n.includes("结构化")) return "attributes";
  if (n.includes("大纲")) return "outline";
  if (n.includes("矩阵")) return "matrix";
  if (n.includes("问答")) return "corpus_qa";
  if (n.includes("撰写") || n.includes("综述")) return "generate";
  return null;
}

function stageState(raw: string): WorkflowCard["state"] {
  if (raw === "active") return "running";
  if (raw === "error") return "error";
  return "done";
}

function processLineToStep(line: ProcessLine): WorkflowStep {
  return {
    key: line.key,
    kind: "tool",
    title: line.title,
    status: line.status,
    preview: line.preview,
    detail: line.detail,
    duration_ms: line.duration_ms,
  };
}

function extensionInlineStep(name: string, data: Record<string, unknown>): WorkflowStep | null {
  if (name === "literature_search_pass_start") {
    const q = String(data.query ?? "").trim();
    const pi = data.pass_index;
    const pt = data.pass_total;
    const passTag =
      typeof pi === "number" && typeof pt === "number" && pt > 1
        ? `（${pi}/${pt}）`
        : "";
    return {
      key: `ext-${name}-${pi ?? 0}`,
      kind: "inline",
      title: q ? `检索中${passTag}：${q.slice(0, 96)}` : `检索中${passTag}`,
      status: "running",
    };
  }
  if (name === "literature_fetch_start") {
    const title = String(data.title ?? "").trim();
    const idx = data.index;
    const total = data.total;
    const n =
      typeof idx === "number" && typeof total === "number"
        ? ` ${idx}/${total}`
        : "";
    const url = String(data.url ?? "").trim();
    let host = "";
    if (url) {
      try {
        host = new URL(url).hostname;
      } catch {
        host = url.slice(0, 40);
      }
    }
    const label = title || host || "网页";
    return {
      key: `ext-${name}-${url || idx || 0}`,
      kind: "inline",
      title: `抓取${n}：${label.slice(0, 72)}`,
      status: "running",
    };
  }
  if (name === "literature_search_refine") {
    const queries = data.queries;
    const n = Array.isArray(queries) ? queries.length : 0;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: n ? `检索式 ×${n}` : "检索式精炼",
      status: "done",
    };
  }
  if (name === "literature_search_merge") {
    const deduped = data.deduped;
    const raw = data.raw_total;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: `合并 ${raw ?? "?"} → 去重 ${deduped ?? "?"}`,
      status: "done",
    };
  }
  if (name === "literature_source") {
    const total = data.total_fetch;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: typeof total === "number" ? `抓取队列 ${total} 篇` : "抓取队列",
      status: "done",
    };
  }
  if (name === "literature_subtopic_plan") {
    const count = data.count;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: typeof count === "number" ? `${count} 个子主题` : "子主题拆分",
      status: "done",
    };
  }
  if (name === "literature_section_refine") {
    const titles = data.target_titles;
    if (Array.isArray(titles) && titles.length) {
      return {
        key: `ext-${name}`,
        kind: "inline",
        title: `修订：${titles.join("、")}`,
        status: "done",
      };
    }
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: "整篇修订",
      status: "done",
    };
  }
  if (name === "literature_paper_index") {
    const count = data.count;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: typeof count === "number" ? `结构化 ${count} 篇` : "文献索引",
      status: "done",
    };
  }
  if (name === "library_updated") {
    const total = data.total;
    return {
      key: `ext-${name}`,
      kind: "inline",
      title: typeof total === "number" ? `文献库 ${total} 篇` : "文献库已更新",
      status: "done",
    };
  }
  return null;
}

export function buildTurnWorkflowFromStream(
  stream: StreamState,
  opts?: {
    processText?: string;
    chatText?: string;
    intent?: string;
    turnIndex?: number;
  },
): TurnWorkflow {
  const trace = collectExecutionTraceFromStream(stream);
  return buildTurnWorkflowFromTrace(trace, {
    extensions: stream.extensionLog.map((e) => ({
      name: e.payload.name,
      data: (e.payload.data ?? {}) as Record<string, unknown>,
    })),
    processText: opts?.processText ?? "",
    chatText: opts?.chatText ?? stream.textContent ?? "",
    intent: opts?.intent,
    turnIndex: opts?.turnIndex ?? 1,
    streaming: stream.status === "streaming",
  });
}

export function buildTurnWorkflowFromTrace(
  trace: ExecutionTrace,
  opts: {
    extensions?: Array<{ name: string; data: Record<string, unknown> }>;
    processText?: string;
    chatText?: string;
    intent?: string;
    turnIndex?: number;
    streaming?: boolean;
    turnWorkflowMeta?: TurnWorkflow;
  },
): TurnWorkflow {
  const cards: WorkflowCard[] = [];
  let activeType: WorkflowCardType = "understand";
  const extByPhase: Record<string, WorkflowStep[]> = {};

  for (const ext of opts.extensions ?? []) {
    const step = extensionInlineStep(ext.name, ext.data);
    if (!step) continue;
    const phase =
      ext.name.includes("search")
        ? "search"
        : ext.name.includes("source") || ext.name.includes("library")
          ? "fetch"
          : ext.name.includes("section")
            ? "revise"
            : ext.name.includes("subtopic")
              ? "understand"
              : ext.name.includes("paper")
                ? "attributes"
                : activeType;
    extByPhase[phase] = extByPhase[phase] ?? [];
    extByPhase[phase].push(step);
  }

  for (const stage of trace.stages) {
    const ctype = stageToCardType(stage.name);
    if (!ctype) continue;
    activeType = ctype;
    const existing = cards.find((c) => c.type === ctype && c.state === "running");
    if (existing) {
      existing.state = stageState(stage.state);
      existing.title = stage.name;
    } else {
      cards.push({
        id: `card-${ctype}-${cards.length}`,
        type: ctype,
        title: stage.name || CARD_TITLES[ctype],
        state: stageState(stage.state),
        steps: [...(extByPhase[ctype] ?? [])],
        locked: ctype === "clarify",
      });
    }
  }

  const toolLines = buildProcessLines(trace).filter((l) => l.kind === "tool");
  const fetchCard = cards.find((c) => c.type === "fetch") ?? cards[cards.length - 1];
  if (fetchCard && toolLines.length) {
    for (const line of toolLines) {
      const step = processLineToStep(line);
      const target =
        line.title.includes("检索") || line.title.includes("web_search")
          ? cards.find((c) => c.type === "search")
          : line.title.includes("引用")
            ? cards.find((c) => c.type === "cite")
            : line.title.includes("attributes") || line.title.includes("结构化")
              ? cards.find((c) => c.type === "attributes")
              : fetchCard;
      if (target && !target.steps.some((s) => s.key === step.key)) {
        target.steps.push(step);
      }
    }
  }

  const processText = (opts.processText ?? "").trim();
  if (processText) {
    cards.unshift({
      id: "card-brief",
      type: "brief",
      title: CARD_TITLES.brief,
      state: "done",
      steps: [],
      body: processText,
    });
  }

  const chatText = (opts.chatText ?? "").trim();
  const intent = opts.intent ?? "new_topic";
  if (intent === "query_corpus" && chatText) {
    cards.push({
      id: "card-corpus-qa",
      type: "corpus_qa",
      title: CARD_TITLES.corpus_qa,
      state: "done",
      steps: [],
      body: chatText.slice(0, 800),
    });
  }

  const clarifying = cards.some(
    (c) => c.type === "clarify" && (c.locked || c.state === "running"),
  );

  const enrichedCards = enrichWorkflowCardSummaries(cards);

  const summaryParts = enrichedCards
    .filter((c) => c.state === "done")
    .map((c) => c.summary || c.title)
    .slice(0, 4);

  return {
    turnIndex: opts.turnIndex ?? 1,
    intent,
    summary: summaryParts.join(" · ") || formatLiteratureIntentLabel(intent),
    cards: enrichedCards,
    clarifying,
  };
}

export function mergeTurnWorkflowMeta(
  meta: TurnWorkflow | undefined,
  trace: ExecutionTrace | undefined,
): TurnWorkflow | null {
  if (meta?.cards?.length) return normalizeTurnWorkflow(meta);
  if (!trace) return null;
  return buildTurnWorkflowFromTrace(trace, {});
}

function normalizeTurnWorkflow(raw: TurnWorkflow): TurnWorkflow {
  return {
    turnIndex: raw.turnIndex ?? 1,
    intent: raw.intent ?? "new_topic",
    summary: raw.summary ?? "",
    clarifying: Boolean(raw.clarifying),
    cards: (raw.cards ?? []).map((c, i) => ({
      id: c.id ?? `card-${i}`,
      type: c.type,
      title: c.title,
      state: c.state ?? "done",
      summary: c.summary,
      steps: c.steps ?? [],
      body: c.body,
      locked: c.locked ?? c.type === "clarify",
    })),
  };
}
