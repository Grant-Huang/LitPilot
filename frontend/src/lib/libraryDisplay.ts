import type { LibraryItem } from "@/lib/libraryTypes";

export const CITATION_FORMAT_OPTIONS = [
  { key: "apa", label: "APA" },
  { key: "acm", label: "ACM" },
] as const;

export type CitationFormatKey = (typeof CITATION_FORMAT_OPTIONS)[number]["key"];

/** 列表序号用于替换引用行首 [n] */
export function formatCitationForList(
  item: LibraryItem,
  format: CitationFormatKey,
  listIndex: number,
): string {
  const citations = item.citations || {};
  const raw =
    citations[format] ||
    citations.apa ||
    citations.acm ||
    "";
  if (!raw) return "";
  return raw.replace(/^\[\d+\]/, `[${listIndex}]`);
}

export function resolveDisplayTitle(item: LibraryItem): string {
  const t = (item.title || "").trim();
  if (t && !/^https?:\/\//i.test(t) && t.length < 200) {
    return t;
  }
  const url = (item.url || "").trim();
  if (!url) return t || "Untitled";
  try {
    const u = new URL(url);
    const seg = u.pathname.split("/").filter(Boolean).pop();
    if (seg) return decodeURIComponent(seg.replace(/\.(html?|pdf)$/i, ""));
    return u.hostname;
  } catch {
    return t || url.slice(0, 80);
  }
}

export function looksLikeAbstract(text: string): boolean {
  const t = text.trim();
  if (t.length < 40) return false;
  if (/^https?:\/\//i.test(t)) return false;
  if (/^#{1,3}\s*https?:\/\//i.test(t)) return false;
  const headerCount = (t.match(/^#{1,3}\s/gm) || []).length;
  if (headerCount > 4 && t.length > 600) return false;
  if (t.includes("diff --git") || t.includes("```json")) return false;
  return true;
}

export function extractAbstractFromFullText(md: string): string {
  const text = (md || "").trim();
  if (!text) return "";
  const patterns = [
    /(?:^|\n)\s*#{1,3}\s*(?:Abstract|ABSTRACT|摘要)\s*\n+([\s\S]*?)(?=\n\s*#{1,3}\s|\n\*\*|\n---\s*\n|$)/i,
    /(?:^|\n)\s*\*\*(?:Abstract|ABSTRACT|摘要)\*\*\s*\n+([\s\S]*?)(?=\n\s*#{1,3}\s|\n\*\*|\n---\s*\n|$)/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m?.[1]) {
      const body = m[1].trim();
      if (body.length >= 24) return body.slice(0, 12_000);
    }
  }
  const paras = text
    .split(/\n{2,}/)
    .map((p) => p.replace(/^#+\s*/, "").trim())
    .filter(
      (p) =>
        p.length >= 80 &&
        !/^https?:\/\//i.test(p) &&
        !p.startsWith("![]") &&
        !p.startsWith("```"),
    );
  if (paras[0]) return paras[0].slice(0, 12_000);
  return "";
}

export function resolveAbstractText(
  item: LibraryItem,
  fullText?: string,
): { text: string; source: "field" | "extracted" | "none" } {
  const field = (item.abstract || "").trim();
  const ft = (fullText || "").trim();
  if (field && looksLikeAbstract(field)) {
    return { text: field, source: "field" };
  }
  const extracted = extractAbstractFromFullText(ft || field);
  if (extracted) return { text: extracted, source: "extracted" };
  if (field && !looksLikeAbstract(field)) {
    return { text: "", source: "none" };
  }
  return { text: field, source: field ? "field" : "none" };
}

export function uniqueProvenanceSessions(
  item: LibraryItem,
): { session_id: string; session_title: string; review_ref_index?: number }[] {
  const seen = new Set<string>();
  const out: {
    session_id: string;
    session_title: string;
    review_ref_index?: number;
  }[] = [];
  for (const p of item.provenance || []) {
    const sid = p.session_id?.trim();
    if (!sid || seen.has(sid)) continue;
    seen.add(sid);
    out.push({
      session_id: sid,
      session_title: p.session_title?.trim() || sid,
      review_ref_index: p.review_ref_index,
    });
  }
  return out;
}

export function openReviewSession(sessionId: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("litpilot:active-session", sessionId);
    window.location.href = "/chat";
  }
}
