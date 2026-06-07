export type LibraryAvailability = {
  has_abstract?: boolean;
  has_full_text?: boolean;
  has_pdf?: boolean;
  fetch_status?: "ok" | "failed" | "blocked" | "pending";
  cite_status?: "ok" | "failed" | "partial" | "pending";
};

export type LibraryProvenance = {
  session_id: string;
  role: string;
  turn_at?: string;
  session_title?: string;
  review_ref_index?: number;
};

export type LibraryItem = {
  id: string;
  display_index: number;
  canonical_key?: string;
  title: string;
  authors: string[];
  venue?: string;
  year?: string;
  month?: string;
  volume?: string;
  issue?: string;
  pages?: string;
  citation_count?: number | null;
  references_count?: number | null;
  references_preview?: { title?: string; year?: string; doi?: string }[];
  url: string;
  doi?: string;
  publisher?: string;
  abstract?: string;
  summary_bullets?: string[];
  full_text?: {
    kind: string;
    path: string;
    char_count?: number;
    fetched_at?: string;
  } | null;
  availability: LibraryAvailability;
  citations?: Record<string, string>;
  provenance?: LibraryProvenance[];
  tags?: string[];
  subtopic_tags?: string[];
  enrich_lite?: {
    method_one_liner?: string;
    findings_one_liner?: string;
    year?: string;
  };
  starred?: boolean;
  updated_at?: string;
};

export function formatAuthors(authors: string[] | undefined): string {
  const list = authors || [];
  if (!list.length) return "作者未知";
  if (list.length <= 3) return list.join(", ");
  return `${list.slice(0, 2).join(", ")} et al.`;
}

/** 兼容旧 index.json 条目 */
export function normalizeLibraryItem(raw: Record<string, unknown>): LibraryItem {
  const authorsRaw = raw.authors;
  const authors = Array.isArray(authorsRaw)
    ? (authorsRaw as string[]).map(String)
    : typeof authorsRaw === "string" && authorsRaw
      ? authorsRaw.split(",").map((s) => s.trim()).filter(Boolean)
      : [];
  return {
    id: String(raw.id || `legacy-${raw.index ?? raw.display_index}`),
    display_index: Number(raw.display_index ?? raw.index ?? 0),
    canonical_key: raw.canonical_key as string | undefined,
    title: String(raw.title || "Untitled"),
    authors,
    venue: String(raw.venue || ""),
    year: String(raw.year || ""),
    month: String(raw.month || ""),
    volume: String(raw.volume || ""),
    issue: String(raw.issue || ""),
    pages: String(raw.pages || ""),
    citation_count: raw.citation_count as number | null | undefined,
    references_count: raw.references_count as number | null | undefined,
    references_preview: Array.isArray(raw.references_preview)
      ? (raw.references_preview as { title?: string; year?: string; doi?: string }[])
      : [],
    url: String(raw.url || ""),
    doi: String(raw.doi || ""),
    publisher: String(raw.publisher || ""),
    abstract: String(raw.abstract || ""),
    availability: (raw.availability as LibraryAvailability) || {
      fetch_status: "pending",
      cite_status: "pending",
    },
    citations: raw.citations as Record<string, string> | undefined,
    provenance: raw.provenance as LibraryProvenance[] | undefined,
    tags: Array.isArray(raw.tags)
      ? (raw.tags as unknown[]).map(String).filter(Boolean)
      : [],
    starred: Boolean(raw.starred),
  };
}

export function formatVenueLine(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.venue) parts.push(item.venue);
  if (item.year) parts.push(item.year);
  const stats = formatCitationStats(item);
  if (stats) parts.push(stats);
  return parts.join(" · ") || "—";
}

function formatCitationStats(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.citation_count != null && item.citation_count > 0) {
    parts.push(`被引 ${item.citation_count}`);
  }
  if (item.references_count != null && item.references_count > 0) {
    parts.push(`他引 ${item.references_count}`);
  }
  return parts.join(" · ");
}
