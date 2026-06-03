import type { ToolCallPayload } from "@meso.ai/ui";

/** Shared step labels — tools and workflow trace use the same wording. */
export const WEB_SEARCH_LABEL = "检索学术文献";
export const WEB_FETCH_LABEL = "抓取网页全文";
export const WEB_FETCH_PREFIX = "抓取网页全文：";
export const EXTRACT_CITATION_LABEL = "抽取引用元数据";
export const EXTRACT_CITATION_PREFIX = "抽取引用元数据：";

function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 48);
  }
}

export function webFetchDisplayTitle(title: string): string {
  const t = title.trim();
  return t || "（暂无标题）";
}

export type WebFetchParsed = {
  articleTitle: string;
  url: string;
  charCount?: number;
};

const WEB_FETCH_CHAR_PREVIEW_RE = /^已抓取正文（约\s*(\d+)\s*字）$/;

export function parseWebFetchCharCountFromOutput(
  output: string | undefined,
): number | undefined {
  const raw = (output ?? "").trim();
  const m = WEB_FETCH_CHAR_PREVIEW_RE.exec(raw);
  if (!m) return undefined;
  const n = parseInt(m[1], 10);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

export function parseWebFetchArgs(
  args: Record<string, unknown> | undefined,
): WebFetchParsed | null {
  const url = String(args?.url ?? "").trim();
  const articleTitle = String(args?.title ?? "").trim();
  if (!url && !articleTitle) return null;
  const rawCount = args?.char_count;
  const charCount =
    typeof rawCount === "number" && rawCount > 0
      ? Math.floor(rawCount)
      : undefined;
  return { articleTitle, url, charCount };
}

export function resolveWebFetchCharCount(
  args: Record<string, unknown> | undefined,
  output: string | undefined,
): number | undefined {
  return (
    parseWebFetchArgs(args)?.charCount ??
    parseWebFetchCharCountFromOutput(output)
  );
}

export function formatWebFetchCharSuffix(charCount: number): string {
  return `（约 ${charCount} 字）`;
}

/** 预览行是否仅为字数摘要（已并入标题 [url] 后，不再单独展示） */
export function isWebFetchCharOnlyPreview(
  output: string | undefined,
  error: string | undefined,
): boolean {
  if ((error ?? "").trim()) return false;
  return parseWebFetchCharCountFromOutput(output) !== undefined;
}

/** 纯文本回退（无障碍 / 复制） */
export function formatWebFetchPlainText(
  articleTitle: string,
  url: string,
  charCount?: number,
): string {
  const title = webFetchDisplayTitle(articleTitle);
  const suffix =
    charCount != null && charCount > 0
      ? formatWebFetchCharSuffix(charCount)
      : "";
  if (!url.trim()) return `${title}${suffix}`;
  return `${title} [url]${suffix}`;
}

export function describeWorkflowKind(name: string): string {
  if (name === "web_fetch") return WEB_FETCH_LABEL;
  if (name === "extract_citation" || name === "cite_extract") {
    return EXTRACT_CITATION_LABEL;
  }
  return name.replace(/_/g, " ");
}

export function describeWorkflowStep(step: {
  name: string;
  title?: string;
  url?: string;
  char_count?: number;
}): string {
  const label = describeWorkflowKind(step.name);
  const wf = webFetchLineMeta(
    step.name,
    undefined,
    step.title,
    step.url,
    step.char_count,
  );
  if (wf) {
    return `${WEB_FETCH_PREFIX}${formatWebFetchPlainText(
      wf.articleTitle,
      wf.url,
      wf.charCount,
    )}`;
  }
  if (step.title) return `${label}：${step.title}`;
  if (step.url) {
    try {
      return `${label}：${new URL(step.url).hostname}`;
    } catch {
      return `${label}：${step.url.slice(0, 48)}`;
    }
  }
  return label;
}

export function describeToolAction(call: ToolCallPayload): string {
  const args = call.args ?? {};
  switch (call.name) {
    case "web_search": {
      const q = String(args.query ?? "").trim();
      return q ? `${WEB_SEARCH_LABEL}：${q}` : WEB_SEARCH_LABEL;
    }
    case "web_fetch": {
      const parsed = parseWebFetchArgs(args as Record<string, unknown>);
      if (!parsed) return WEB_FETCH_LABEL;
      return `${WEB_FETCH_PREFIX}${formatWebFetchPlainText(
        parsed.articleTitle,
        parsed.url,
        parsed.charCount,
      )}`;
    }
    case "extract_citation": {
      const url = String(args.url ?? "").trim();
      const title = String(args.title ?? "").trim();
      if (title) return `${EXTRACT_CITATION_PREFIX}${title}`;
      return url
        ? `${EXTRACT_CITATION_PREFIX}${hostFromUrl(url)}`
        : EXTRACT_CITATION_LABEL;
    }
    default:
      return call.name.replace(/_/g, " ");
  }
}

/** 折叠行预览：取结果首行，过长则截断 */
export function previewToolResult(
  output: string | undefined,
  error: string | undefined,
  maxLen = 100,
): string {
  const raw = (error || output || "").trim();
  if (!raw) return "（无输出）";

  let line = raw;
  if (callLooksJson(raw)) {
    try {
      const data = JSON.parse(raw) as Record<string, unknown>;
      if (typeof data.hits === "number") {
        const ans = String(data.answer ?? "").trim();
        line = ans
          ? `命中 ${data.hits} 条；${ans}`
          : `命中 ${data.hits} 条文献`;
      } else if (data.answer) {
        line = String(data.answer);
      }
    } catch {
      /* keep raw */
    }
  }

  const first = line.split(/\r?\n/).find((l) => l.trim())?.trim() ?? line;
  const oneLine = first.replace(/\s+/g, " ");
  if (oneLine.length <= maxLen) return oneLine;
  return `${oneLine.slice(0, maxLen)}…`;
}

function callLooksJson(s: string): boolean {
  const t = s.trim();
  return t.startsWith("{") && t.endsWith("}");
}

export function isWebFetchLine(
  name: string,
  args?: Record<string, unknown>,
  url?: string,
): boolean {
  if (name !== "web_fetch") return false;
  return Boolean(parseWebFetchArgs(args) || url?.trim());
}

export function webFetchLineMeta(
  name: string,
  args?: Record<string, unknown>,
  title?: string,
  url?: string,
  charCount?: number,
  output?: string,
): WebFetchParsed | null {
  if (name !== "web_fetch") return null;
  const fromArgs = parseWebFetchArgs(args);
  if (fromArgs) {
    if (fromArgs.charCount == null) {
      const fromOut = parseWebFetchCharCountFromOutput(output);
      if (fromOut != null) return { ...fromArgs, charCount: fromOut };
    }
    return fromArgs;
  }
  const u = (url ?? "").trim();
  if (!u) return null;
  const count =
    charCount ??
    parseWebFetchCharCountFromOutput(output) ??
    undefined;
  return { articleTitle: (title ?? "").trim(), url: u, charCount: count };
}
