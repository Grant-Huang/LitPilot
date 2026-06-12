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
  /** Frozen think snapshot when a phase completes (see literature_phase_think). */
  pinnedThink?: string;
  locked?: boolean;
  subTopics?: Array<{ id: string; title: string; search_query: string }>;
  /**
   * Cached extension data for search subtopic progress (search_done / filter_done
   * / source_done). Used by SearchProgressView when live extensions are unavailable
   * (e.g. completed turn view).
   */
  progressExtensions?: Array<{ name: string; data: Record<string, unknown> }>;
};

export type TurnWorkflow = {
  turnIndex: number;
  intent: string;
  summary: string;
  cards: WorkflowCard[];
};

const CARD_TITLES: Record<WorkflowCardType, string> = {
  understand: "理解研究问题",
  brief: "研究计划",
  search: "文献检索",
  fetch: "抓取全文",
  cite: "引用抽取",
  attributes: "文献结构化",
  outline: "大纲规划",
  generate: "综述生成",
  matrix: "文献矩阵",
  corpus_qa: "语料问答",
  clarify: "等待澄清",
  manage: "文献库操作",
};

function phaseThinkStageToCardType(stageKey: string): WorkflowCardType | null {
  const key = stageKey.trim().toLowerCase();
  if (key === "brief") return "brief";
  if (key === "search") return "search";
  if (key === "understand" || key === "understanding") return "understand";
  return null;
}

function stageToCardType(name: string): WorkflowCardType | null {
  const n = name.trim();
  if (!n || n === "完成" || n === "继续撰写") return null;
  if (n.includes("理解") || n.includes("意图")) return "understand";
  if (n === "Brief" || n.includes("brief") || n.includes("Brief")) return "brief";
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
  if (
    name === "literature_subtopic_plan" ||
    name === "literature_subtopic_search_done" ||
    name === "literature_subtopic_filter_done" ||
    name === "literature_subtopic_fetch_done" ||
    name === "literature_generate_done"
  ) {
    return null;
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

const CHAT_INTENTS = new Set(["query_corpus"]);

export function workflowNeedsChat(intent: string): boolean {
  return CHAT_INTENTS.has(intent);
}

export function deriveLiveFieldsFromStream(stream: StreamState): {
  intent: string;
  /** @deprecated 仅含 brief 结构化结果；勿用于 progress 心跳 */
  processText: string;
  liveProgressDetail: string;
  briefSummary: string;
  chatText: string;
} {
  let intent = "new_topic";
  let processDelta = "";
  let progressDetail = "";
  let briefParts = "";

  for (const ext of stream.extensionLog) {
    const name = ext.payload.name;
    const data = (ext.payload.data ?? {}) as Record<string, unknown>;
    if (name === "turn_start" && typeof data.intent === "string") {
      intent = data.intent;
      processDelta = "";
    }
    if (name === "literature_intent" && typeof data.intent === "string") {
      intent = data.intent;
    }
    if (name === "process_text" && typeof data.delta === "string") {
      processDelta += data.delta;
    }
    if (name === "literature_brief_assessment") {
      const rq = Array.isArray(data.core_research_questions)
        ? (data.core_research_questions as string[]).join("；")
        : "";
      const kw = Array.isArray(data.keywords)
        ? (data.keywords as string[]).join("、")
        : "";
      const hint =
        typeof data.search_query_hint === "string" ? data.search_query_hint : "";
      const parts = [
        rq ? `RQ：${rq}` : "",
        kw ? `关键词：${kw}` : "",
        hint ? `检索 hint：${hint}` : "",
      ].filter(Boolean);
      if (parts.length) briefParts = parts.join("\n");
    }
    if (name === "literature_progress" && typeof data.detail === "string") {
      const detail = data.detail.trim();
      if (detail) progressDetail = detail;
    }
  }

  const briefSummary = briefParts.trim();
  const liveProgressDetail = (progressDetail || processDelta).trim();
  const chatText = workflowNeedsChat(intent)
    ? (stream.textContent ?? "").slice(0, 800)
    : "";

  return {
    intent,
    processText: briefSummary,
    liveProgressDetail,
    briefSummary,
    chatText,
  };
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
  const derived = deriveLiveFieldsFromStream(stream);
  const trace = collectExecutionTraceFromStream(stream);
  return buildTurnWorkflowFromTrace(trace, {
    extensions: stream.extensionLog.map((e) => ({
      name: e.payload.name,
      data: (e.payload.data ?? {}) as Record<string, unknown>,
    })),
    briefSummary: derived.briefSummary,
    chatText: opts?.chatText ?? derived.chatText,
    intent: opts?.intent ?? derived.intent,
    turnIndex: opts?.turnIndex ?? 1,
    streaming: stream.status === "streaming",
  });
}

const THINK_STREAM_CARD_TYPES = new Set<WorkflowCardType>([
  "understand",
  "brief",
  "search",
]);

/** Pick the card title: for "分析用户意图" stage use it directly instead of the fixed CARD_TITLES.understand. */
function _cardTitle(ctype: WorkflowCardType, stageName: string): string {
  if (ctype === "understand" && stageName.includes("意图")) return stageName;
  return CARD_TITLES[ctype] || stageName;
}

export function buildTurnWorkflowFromTrace(
  trace: ExecutionTrace,
  opts: {
    extensions?: Array<{ name: string; data: Record<string, unknown> }>;
    /** @deprecated 使用 briefSummary */
    processText?: string;
    briefSummary?: string;
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
  let subTopics: WorkflowCard["subTopics"];

  for (const ext of opts.extensions ?? []) {
    if (ext.name === "literature_subtopic_plan") {
      const raw = ext.data.subtopics ?? ext.data.sub_topics;
      if (Array.isArray(raw)) {
        subTopics = raw.map((st, i) => {
          const row = st as Record<string, unknown>;
          return {
            id: String(row.id ?? `sub-${i}`),
            title: String(row.title ?? ""),
            search_query: String(row.search_query ?? ""),
          };
        });
      }
      continue;
    }
    const step = extensionInlineStep(ext.name, ext.data);
    if (!step) continue;
    const phase =
      ext.name.includes("search")
        ? "search"
        : ext.name.includes("source") || ext.name.includes("library")
          ? "fetch"
          : ext.name.includes("section")
            ? "generate"
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
      existing.title = _cardTitle(ctype, stage.name);
    } else {
      cards.push({
        id: `card-${ctype}-${cards.length}`,
        type: ctype,
        title: _cardTitle(ctype, stage.name),
        state: stageState(stage.state),
        steps: [...(extByPhase[ctype] ?? [])],
        locked: ctype === "clarify",
      });
    }
  }

  // Turn complete: promote any lingering "running" cards to "done" (round 4 #4).
  // Backend sometimes emits stage "active" without a paired "done" before the next
  // stage starts (e.g. search→fetch), leaving the card stuck "running" after
  // streaming ends. That makes canToggle=false so the title isn't clickable.
  if (!opts.streaming) {
    for (const card of cards) {
      if (card.state === "running") card.state = "done";
    }
  }

  for (const ext of opts.extensions ?? []) {
    if (ext.name === "literature_phase_think") {
      const content = String(ext.data.content ?? "").trim();
      if (!content) continue;
      const ctype = phaseThinkStageToCardType(String(ext.data.stage ?? ""));
      if (!ctype) continue;
      const target = cards.find((c) => c.type === ctype);
      if (target) {
        target.pinnedThink = content;
      }
      continue;
    }
    if (ext.name !== "literature_progress") continue;
    const detail = String(ext.data.detail ?? "").trim();
    if (!detail) continue;
    const stageKey = String(ext.data.stage ?? "");
    const targetType =
      stageKey === "brief"
        ? "brief"
        : stageKey === "understand" || stageKey === "understanding"
          ? "understand"
          : activeType;
    const target = cards.find((c) => c.type === targetType && c.state === "running");
    // THINK_STREAM 类卡片（understand / brief / search）的内容由 thinkfold 全权渲染，
    // 不要再把 progress.detail 写入 body 制造与 thinkfold 内容重复、并在 stage 结束
    // 那一刻"刷一下"出现的格式跳变。brief 卡的结构化 RQ+关键词由 briefSummary
    // 合并块单独负责（见下方）。
    if (target && !target.body && !THINK_STREAM_CARD_TYPES.has(target.type)) {
      target.body = detail;
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
      // Search card 永远不挂任何 tool step：SubtopicBlock 的 SourceRow / 过滤详情
      // 已经完整呈现"哪一轮查了哪个源、命中多少篇、为何被剔除"。再在 card 顶层
      // 重复一行 raw tool log 只会孤立飘在子主题列表之外（round 2/3 审查 #6/#7）。
      // 后端如果在 tool meta 里加上 subtopic_id，可以恢复"按子主题挂步骤"的能力。
      if (target?.type === "search") {
        continue;
      }
      if (target && !target.steps.some((s) => s.key === step.key)) {
        target.steps.push(step);
      }
    }
  }

  // 结构化 RQ + 关键词：优先合并到已有的 brief 卡（来自 stage emit），没有时再新增。
  // 避免出现两张 brief 卡片（一张来自 stage，一张来自 briefSummary）。
  const briefSummary = (opts.briefSummary ?? opts.processText ?? "").trim();
  if (briefSummary) {
    const existingBrief = cards.find((c) => c.type === "brief");
    if (existingBrief) {
      existingBrief.body = briefSummary;
    } else {
      cards.splice(cards.length === 0 ? 0 : 1, 0, {
        id: "card-brief",
        type: "brief",
        title: CARD_TITLES.brief,
        state: "done",
        steps: [],
        body: briefSummary,
      });
    }
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

  const summarizeCtx = {
    trace,
    extensions: opts.extensions,
  };
  const enrichedCards = enrichWorkflowCardSummaries(cards, summarizeCtx).map((c) => {
    if (subTopics?.length && (c.type === "understand" || c.type === "search")) {
      return { ...c, subTopics };
    }
    return c;
  });

  // Canonical 阶段顺序：后端 stage emit 顺序若被打乱，前端兜底排序。
  // 例如曾出现 "抓取全文" 显示在 "文献检索" 之前的 bug（round 3 审查 #3）。
  const CANONICAL_ORDER: WorkflowCardType[] = [
    "understand", "brief", "search", "fetch", "cite", "attributes",
    "outline", "generate", "matrix", "corpus_qa", "clarify", "manage",
  ];
  const orderIdx = (c: WorkflowCard) => {
    const i = CANONICAL_ORDER.indexOf(c.type);
    return i < 0 ? 999 : i;
  };
  enrichedCards.sort((a, b) => orderIdx(a) - orderIdx(b));

  let mergedKept = 0;
  let hasFilter = false;
  for (const ext of opts.extensions ?? []) {
    if (ext.name !== "literature_subtopic_filter_done") continue;
    const kept = ext.data.kept_count;
    if (typeof kept === "number") {
      mergedKept += kept;
      hasFilter = true;
    }
  }
  if (hasFilter) {
    const searchCard = enrichedCards.find((c) => c.type === "search");
    if (searchCard) {
      searchCard.summary = `纳入 ${mergedKept} 篇`;
    }
  }

  // Cache search progress extensions into the search card so that the completed
  // turn view (LitPilotAssistantTurn, which has no access to raw streaming
  // extensionLog) can still render subtopic search/filter details.
  const searchCard = enrichedCards.find((c) => c.type === "search");
  if (searchCard && opts.extensions?.length) {
    const progressExts = opts.extensions.filter(
      (ext) =>
        ext.name === "literature_search_source_done" ||
        ext.name === "literature_subtopic_search_done" ||
        ext.name === "literature_subtopic_filter_done" ||
        ext.name === "literature_subtopic_fetch_done",
    );
    if (progressExts.length > 0) {
      searchCard.progressExtensions = progressExts;
    }
  }

  const runningCard = enrichedCards.find((c) => c.state === "running");
  const summaryParts = enrichedCards
    .filter((c) => c.state === "done")
    .map((c) => c.summary || c.title)
    .slice(0, 4);

  const summary = opts.streaming
    ? runningCard?.title || formatLiteratureIntentLabel(intent)
    : summaryParts.join(" · ") || formatLiteratureIntentLabel(intent);

  return {
    turnIndex: opts.turnIndex ?? 1,
    intent,
    summary,
    cards: enrichedCards,
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
    cards: (raw.cards ?? []).map((c, i) => ({
      id: c.id ?? `card-${i}`,
      type: c.type,
      title: c.title,
      state: c.state ?? "done",
      summary: c.summary,
      steps: c.steps ?? [],
      body: c.body,
      pinnedThink: c.pinnedThink,
      locked: c.locked ?? false,
      subTopics: c.subTopics,
      progressExtensions: c.progressExtensions,
    })),
  };
}
