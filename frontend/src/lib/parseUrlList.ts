const URL_RE = /https?:\/\/[^\s<>'"]+/gi;
const MAX_URLS = 20;

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

export function parseUrlsFromText(text: string): string[] {
  const found = (text.match(URL_RE) ?? [])
    .map((m) => normalizeUrl(m))
    .filter((u): u is string => Boolean(u));
  return dedupe(found).slice(0, MAX_URLS);
}

function parseUrlsFromLines(text: string): string[] {
  const urls: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    if (/https?:\/\//i.test(trimmed)) {
      urls.push(...parseUrlsFromText(trimmed));
      continue;
    }
    for (const cell of trimmed.split(/[\t,;|]/)) {
      const u = normalizeUrl(cell);
      if (u) urls.push(u);
    }
  }
  return dedupe(urls).slice(0, MAX_URLS);
}

function parseUrlsFromJson(text: string): string[] {
  const data: unknown = JSON.parse(text);
  const urls: string[] = [];

  const walk = (node: unknown): void => {
    if (typeof node === "string") {
      const u = normalizeUrl(node);
      if (u) urls.push(u);
      else urls.push(...parseUrlsFromText(node));
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
  return dedupe(urls).slice(0, MAX_URLS);
}

export async function parseUrlListFile(file: File): Promise<string[]> {
  const text = await file.text();
  const name = file.name.toLowerCase();

  if (name.endsWith(".json")) {
    try {
      return parseUrlsFromJson(text);
    } catch {
      /* fall through */
    }
  }

  const fromLines = parseUrlsFromLines(text);
  if (fromLines.length) return fromLines;
  return parseUrlsFromText(text);
}
