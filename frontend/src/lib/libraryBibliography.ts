import type { LibraryItem } from "./libraryTypes";

export type ReferencePreview = {
  title?: string;
  year?: string;
  doi?: string;
};

export function formatBibliographicLine(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.venue) parts.push(item.venue);
  if (item.year) parts.push(String(item.year));
  if (item.month) parts.push(`${item.month}月`);
  const volIssue: string[] = [];
  if (item.volume) volIssue.push(`Vol. ${item.volume}`);
  if (item.issue) volIssue.push(`No. ${item.issue}`);
  if (volIssue.length) parts.push(volIssue.join(" "));
  if (item.pages) parts.push(`pp. ${item.pages}`);
  return parts.join(" · ") || "—";
}

export function formatCitationStats(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.citation_count != null) {
    parts.push(`被引 ${item.citation_count}`);
  }
  if (item.references_count != null) {
    parts.push(`他引 ${item.references_count}`);
  }
  return parts.join(" · ");
}

export function hasBibliographicBasics(item: LibraryItem): boolean {
  return Boolean(
    item.title ||
      item.authors?.length ||
      item.venue ||
      item.year ||
      item.doi,
  );
}
