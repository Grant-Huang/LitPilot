import type { ToolCallPayload } from "@meso/ui";

function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 48);
  }
}

export function describeToolAction(call: ToolCallPayload): string {
  const args = call.args ?? {};
  switch (call.name) {
    case "web_search": {
      const q = String(args.query ?? "").trim();
      return q ? `检索学术文献：${q}` : "检索学术文献";
    }
    case "web_fetch": {
      const url = String(args.url ?? "").trim();
      const title = String(args.title ?? "").trim();
      if (title) return `抓取网页全文：${title}`;
      return url ? `抓取网页全文：${hostFromUrl(url)}` : "抓取网页全文";
    }
    case "extract_citation": {
      const url = String(args.url ?? "").trim();
      const title = String(args.title ?? "").trim();
      if (title) return `抽取引用元数据：${title}`;
      return url ? `抽取引用元数据：${hostFromUrl(url)}` : "抽取引用元数据";
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
