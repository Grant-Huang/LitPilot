import { message } from "antd";
import { formatLiteratureIntentLabel } from "@/lib/literatureIntent";

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

const HANDLERS: Record<string, ExtensionHandler> = {
  literature_intent: (data, ctx) => {
    if (!ctx.isChat) return;
    const intent = data?.intent;
    if (typeof intent === "string") {
      message.info(formatLiteratureIntentLabel(intent));
    }
  },
  literature_search_plan: (data, ctx) => {
    if (!ctx.isChat) return;
    const queries = data?.queries;
    if (Array.isArray(queries) && queries.length) {
      message.info(`检索扩展：${queries.length} 组 query`);
    }
  },
  literature_paper_index: (data, ctx) => {
    if (!ctx.isChat) return;
    const count = data?.count;
    const extracted = data?.extracted;
    if (typeof count === "number") {
      message.info(
        `文献结构化：${count} 篇${typeof extracted === "number" ? `（本轮 +${extracted}）` : ""}`,
      );
    }
  },
  literature_subtopic_plan: (data, ctx) => {
    if (!ctx.isChat) return;
    const count = data?.count;
    if (typeof count === "number" && count >= 2) {
      message.info(`已拆分为 ${count} 个子主题，将分别检索`);
    }
  },
  literature_outline: (data, ctx) => {
    if (!ctx.isChat) return;
    const sectionCount = data?.section_count;
    if (typeof sectionCount === "number") {
      message.info(`大纲已生成：${sectionCount} 个章节（见右侧「大纲」）`);
    }
  },
  literature_refine_report: (data, ctx) => {
    if (!ctx.isChat) return;
    const missing = data?.missing_sections;
    if (Array.isArray(missing) && missing.length) {
      message.warning(`后处理：${missing.length} 个章节标题未在正文中出现`);
    }
  },
  literature_section_refine: (data, ctx) => {
    if (!ctx.isChat) return;
    const mode = data?.mode;
    const titles = data?.target_titles;
    if (mode === "partial" && Array.isArray(titles) && titles.length) {
      message.info(`章节级修订：${titles.join("、")}`);
    }
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
