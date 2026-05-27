import { MAX_FETCH_URLS_CAP, clampFetchUrlLimit } from "@/lib/fetchUrlLimits";

const URL_RE = /https?:\/\/[^\s<>'"]+/gi;

export type ParseUrlListResult = {
  urls: string[];
  /** 去重后、截断前的条数 */
  totalFound: number;
  limit: number;
  truncated: boolean;
};

function normalizeUrl(raw: string): string | null {
  let u = raw.trim().replace(/[.,;)]+$/, "");
  if (!u) return null;
  if (!/^https?:\/\//i.test(u)) {
    if (u.startsWith("www.")) u = `https://${u}`;
    else return null;
  }
  try {
    const parsed = new URL(u);
    if (!parsed.hostname) return null;
    return u;
  } catch {
    return null;
  }
}

function dedupe(urls: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const u of urls) {
    if (seen.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}

function applyLimit(urls: string[], limit: number): ParseUrlListResult {
  const cap = clampFetchUrlLimit(limit);
  const totalFound = urls.length;
  return {
    urls: urls.slice(0, cap),
    totalFound,
    limit: cap,
    truncated: totalFound > cap,
  };
}

export function parseUrlsFromText(
  text: string,
  limit = MAX_FETCH_URLS_CAP,
): ParseUrlListResult {
  return applyLimit(dedupe(extractUrlsFromText(text)), limit);
}

function extractUrlsFromText(text: string): string[] {
  return (text.match(URL_RE) ?? [])
    .map((m) => normalizeUrl(m))
    .filter((u): u is string => Boolean(u));
}

function parseUrlsFromLines(text: string, limit: number): ParseUrlListResult {
  const urls: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    if (/https?:\/\//i.test(trimmed)) {
      urls.push(...extractUrlsFromText(trimmed));
      continue;
    }
    for (const cell of trimmed.split(/[\t,;|]/)) {
      const u = normalizeUrl(cell);
      if (u) urls.push(u);
    }
  }
  return applyLimit(dedupe(urls), limit);
}

function parseUrlsFromJson(text: string, limit: number): ParseUrlListResult {
  const data: unknown = JSON.parse(text);
  const urls: string[] = [];

  const walk = (node: unknown): void => {
    if (typeof node === "string") {
      const u = normalizeUrl(node);
      if (u) urls.push(u);
      else urls.push(...extractUrlsFromText(node));
    } else if (Array.isArray(node)) {
      node.forEach(walk);
    } else if (node && typeof node === "object") {
      const obj = node as Record<string, unknown>;
      for (const key of ["url", "link", "href", "urls", "links"]) {
        if (key in obj) walk(obj[key]);
      }
      Object.values(obj).forEach((v) => {
        if (Array.isArray(v) || (v && typeof v === "object")) walk(v);
      });
    }
  };

  walk(data);
  return applyLimit(dedupe(urls), limit);
}

export async function parseUrlListFile(
  file: File,
  limit: number = MAX_FETCH_URLS_CAP,
): Promise<ParseUrlListResult> {
  const text = await file.text();
  const name = file.name.toLowerCase();
  const cap = clampFetchUrlLimit(limit);

  if (name.endsWith(".json")) {
    try {
      return parseUrlsFromJson(text, cap);
    } catch {
      /* fall through */
    }
  }

  const fromLines = parseUrlsFromLines(text, cap);
  if (fromLines.urls.length) return fromLines;
  return parseUrlsFromText(text, cap);
}
