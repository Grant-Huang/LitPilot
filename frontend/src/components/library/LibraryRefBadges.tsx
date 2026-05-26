"use client";

import type { LibraryItem } from "@/lib/libraryTypes";
import { provenanceLabel } from "@/lib/libraryListUtils";

export type LibraryBadgeAction = {
  key: string;
  label: string;
  title: string;
  href?: string;
  variant?: "default" | "pdf" | "doi" | "warn" | "muted";
  onClick?: () => void;
};

const MAX_BADGES = 3;

export function buildLibraryBadgeActions(item: LibraryItem): LibraryBadgeAction[] {
  const av = item.availability || {};
  const actions: LibraryBadgeAction[] = [];

  if (av.has_full_text) {
    actions.push({
      key: "fulltext",
      label: "全文",
      title: "在详情中查看全文",
    });
  }
  if (av.has_pdf && item.full_text?.path?.includes("pdfs/")) {
    const name = item.full_text.path.replace(/^pdfs\//, "");
    actions.push({
      key: "pdf",
      label: "PDF",
      title: "打开 PDF",
      href: `/api/library/pdfs/${encodeURIComponent(name)}`,
      variant: "pdf",
    });
  }
  if (item.doi) {
    actions.push({
      key: "doi",
      label: "DOI",
      title: `https://doi.org/${item.doi}`,
      href: `https://doi.org/${item.doi}`,
      variant: "doi",
    });
  }
  if (item.url) {
    actions.push({
      key: "link",
      label: "原文",
      title: item.url,
      href: item.url,
      variant: "default",
    });
  }
  if (av.fetch_status === "failed") {
    actions.push({
      key: "fetch-fail",
      label: "抓取失败",
      title: "网页抓取失败",
      variant: "warn",
    });
  }
  if (av.cite_status === "failed") {
    actions.push({
      key: "cite-fail",
      label: "引用失败",
      title: "引用元数据抽取失败",
      variant: "warn",
    });
  }
  const prov = item.provenance?.length ?? 0;
  if (prov > 0) {
    actions.push({
      key: "prov",
      label: provenanceLabel(prov),
      title: `出现在 ${prov} 个综述会话`,
      variant: "muted",
    });
  }

  const priority = ["fetch-fail", "cite-fail", "fulltext", "pdf", "doi", "link", "prov"];
  const sorted = [...actions].sort(
    (a, b) => priority.indexOf(a.key) - priority.indexOf(b.key),
  );
  return sorted.slice(0, MAX_BADGES);
}

type Props = {
  item: LibraryItem;
  onOpenDetail?: (action: LibraryBadgeAction) => void;
};

export function LibraryRefBadges({ item, onOpenDetail }: Props) {
  const badges = buildLibraryBadgeActions(item);

  return (
    <div className="library-ref-card__badges" aria-label="文献状态">
      {badges.map((b) => {
        const cls = `library-badge library-badge--action${
          b.variant ? ` library-badge--${b.variant}` : ""
        }`;
        if (b.href) {
          return (
            <a
              key={b.key}
              className={cls}
              href={b.href}
              target="_blank"
              rel="noreferrer"
              title={b.title}
              onClick={(e) => e.stopPropagation()}
            >
              {b.label}
            </a>
          );
        }
        return (
          <button
            key={b.key}
            type="button"
            className={cls}
            title={b.title}
            onClick={(e) => {
              e.stopPropagation();
              if (b.key === "fulltext" && onOpenDetail) {
                onOpenDetail(b);
              }
            }}
          >
            {b.label}
          </button>
        );
      })}
    </div>
  );
}
