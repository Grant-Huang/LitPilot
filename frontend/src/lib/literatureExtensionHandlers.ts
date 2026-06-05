import { formatLiteratureIntentLabel } from "@/lib/literatureIntent";
import { toastInfo, toastWarning } from "@/lib/toastFeedback";

type ExtensionData = Record<string, unknown> | undefined;

type HandlerContext = {
  isChat: boolean;
  setActiveSessionId: (id: string) => void;
  loadSessions: () => Promise<void>;
  persistActiveSession: (id: string) => void;
};

type ExtensionHandler = (
  data: ExtensionData,
  ctx: HandlerContext,
) => void;

const CLARIFICATION_LABELS: Record<string, string> = {
  first_turn: "请补充研究主题",
  search_zero: "检索无命中，请选择下一步",
  outline_confirm: "请确认大纲后继续",
};

const HANDLERS: Record<string, ExtensionHandler> = {
  literature_intent: (data, ctx) => {
    if (!ctx.isChat) return;
    const intent = data?.intent;
    if (typeof intent === "string") {
      toastInfo(formatLiteratureIntentLabel(intent));
    }
  },
  literature_source: (data, ctx) => {
    if (!ctx.isChat) return;
    const userCount = data?.user_count;
    const searchHitCount = data?.search_hit_count;
    const totalFetch = data?.total_fetch;
    const mode = data?.mode;
    if (typeof totalFetch !== "number") return;
    const parts: string[] = [];
    if (typeof userCount === "number" && userCount > 0) {
      parts.push(`上传 ${userCount} 条优先`);
    }
    if (typeof searchHitCount === "number" && searchHitCount > 0) {
      parts.push(`检索 ${searchHitCount} 条`);
    }
    const mergeHint = parts.length ? parts.join(" + ") : "仅检索命中";
    const provider =
      typeof data?.fetch_provider === "string" ? data.fetch_provider : "";
    const cap =
      typeof data?.fetch_cap === "number" ? `，上限 ${data.fetch_cap}` : "";
    const providerHint = provider ? ` · ${provider}` : "";
    toastInfo(
      `web_fetch 队列：${mergeHint} → 本轮抓取 ${totalFetch} 篇${cap}${providerHint}${mode === "merge" ? "（合并模式）" : mode === "user_only" ? "（仅用户列表）" : ""}`,
      10,
    );
  },
  literature_search_plan: (data, ctx) => {
    if (!ctx.isChat) return;
    const queries = data?.queries;
    if (Array.isArray(queries) && queries.length) {
      toastInfo(`检索扩展：${queries.length} 组 query`);
    }
  },
  literature_search_merge: (data, ctx) => {
    if (!ctx.isChat) return;
    const passCounts = data?.pass_hit_counts;
    const raw = data?.raw_total;
    const deduped = data?.deduped;
    const toolTotal = data?.tool_hit_total;
    const preCorpus = data?.raw_before_corpus;
    const dropped = data?.corpus_dropped;
    if (process.env.NODE_ENV === "development") {
      console.info("[LitPilot] literature_search_merge", data);
    }
    if (!Array.isArray(passCounts)) return;
    const rounds = passCounts.map((n) => String(n)).join(" / ");
    const hint =
      typeof raw === "number" &&
      typeof deduped === "number" &&
      raw > 0 &&
      deduped === 0
        ? "（合并为 0：多为语料 URL 去重）"
        : typeof toolTotal === "number" &&
            toolTotal > 0 &&
            typeof raw === "number" &&
            raw === 0
          ? "（各轮未写入 pass_out，属后端落盘异常）"
          : "";
    const text =
      `检索合并：各轮 ${rounds} → pass合计 ${raw ?? "?"}，去重后 ${deduped ?? "?"}${hint}` +
      (typeof preCorpus === "number" && preCorpus !== raw
        ? `；过滤前 ${preCorpus}`
        : "") +
      (typeof dropped === "number" && dropped > 0 ? `；语料剔除 ${dropped}` : "");
    if (hint.includes("合并为 0") || hint.includes("未写入")) {
      toastWarning(text, 12);
    } else {
      toastInfo(text, 8);
    }
  },
  literature_paper_index: (data, ctx) => {
    if (!ctx.isChat) return;
    const count = data?.count;
    const extracted = data?.extracted;
    if (typeof count === "number") {
      toastInfo(
        `文献结构化：${count} 篇${typeof extracted === "number" ? `（本轮 +${extracted}）` : ""}`,
      );
    }
  },
  literature_subtopic_plan: (data, ctx) => {
    if (!ctx.isChat) return;
    const count = data?.count;
    if (typeof count === "number" && count >= 2) {
      toastInfo(`已拆分为 ${count} 个子主题，将分别检索`);
    }
  },
  literature_outline: (data, ctx) => {
    if (!ctx.isChat) return;
    const sectionCount = data?.section_count;
    if (typeof sectionCount === "number") {
      toastInfo(`大纲已生成：${sectionCount} 个章节（见右侧「大纲」）`);
    }
  },
  literature_refine_report: (data, ctx) => {
    if (!ctx.isChat) return;
    const missing = data?.missing_sections;
    if (Array.isArray(missing) && missing.length) {
      toastWarning(`后处理：${missing.length} 个章节标题未在正文中出现`);
    }
  },
  literature_section_refine: (data, ctx) => {
    if (!ctx.isChat) return;
    const mode = data?.mode;
    const titles = data?.target_titles;
    if (mode === "partial" && Array.isArray(titles) && titles.length) {
      toastInfo(`章节级修订：${titles.join("、")}`);
    }
  },
  literature_clarification: (data, ctx) => {
    if (!ctx.isChat) return;
    const kind = typeof data?.kind === "string" ? data.kind : "";
    const label = CLARIFICATION_LABELS[kind];
    if (label) toastInfo(label);
  },
  literature_brief_assessment: (_data, _ctx) => {
    /* RQ/关键词已在对话正文中展示，此处不再 toast */
  },
  session: (data, ctx) => {
    const sid = data?.session_id;
    if (typeof sid !== "string" || !sid) return;
    ctx.setActiveSessionId(sid);
    ctx.persistActiveSession(sid);
    void ctx.loadSessions();
  },
  session_title: (_data, ctx) => {
    void ctx.loadSessions();
  },
};

export function handleLiteratureExtensionEvent(
  name: string,
  data: ExtensionData,
  ctx: HandlerContext,
): void {
  const handler = HANDLERS[name];
  if (handler) handler(data, ctx);
}
