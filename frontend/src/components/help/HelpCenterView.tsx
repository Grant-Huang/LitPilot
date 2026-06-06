"use client";

import { useCallback, useMemo } from "react";
import { QuestionCircleOutlined } from "@ant-design/icons";
import {
  getHelpPage,
  HELP_CATEGORIES,
  HELP_PAGES,
  HELP_PAGE_MAP,
  type HelpPageId,
} from "@/content/help";
import { renderHelpBodyHtml } from "@/content/help/renderHelpBody";
import { FunctionalDocShell, type DocShellNavGroup } from "@/components/layout/FunctionalDocShell";

type Props = {
  pageId: HelpPageId;
  onPageChange: (id: HelpPageId) => void;
};

function HelpBody({
  body,
  onNavigate,
}: {
  body: string;
  onNavigate: (id: HelpPageId) => void;
}) {
  const html = useMemo(() => renderHelpBodyHtml(body), [body]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement | null;
      const btn = target?.closest?.("button[data-help-page]");
      if (!btn) return;
      const id = btn.getAttribute("data-help-page") as HelpPageId | null;
      if (id && HELP_PAGE_MAP[id]) {
        event.preventDefault();
        onNavigate(id);
      }
    },
    [onNavigate],
  );

  if (!html) {
    return <div className="help-center__body" />;
  }

  return (
    <div
      className="help-center__body help-center__md"
      dangerouslySetInnerHTML={{ __html: html }}
      onClick={handleClick}
    />
  );
}

function buildHelpNavGroups(pageId: HelpPageId, onPageChange: (id: HelpPageId) => void): DocShellNavGroup[] {
  return HELP_CATEGORIES.map((cat) => ({
    id: cat,
    label: cat,
    items: HELP_PAGES.filter((p) => p.category === cat).map((p) => ({
      id: p.id,
      label: p.title,
      active: p.id === pageId,
      onClick: () => onPageChange(p.id),
    })),
  })).filter((group) => group.items.length > 0);
}

export function HelpCenterView({ pageId, onPageChange }: Props) {
  const page = getHelpPage(pageId);
  const navGroups = useMemo(
    () => buildHelpNavGroups(pageId, onPageChange),
    [pageId, onPageChange],
  );

  const handleNavigate = useCallback(
    (id: HelpPageId) => {
      onPageChange(id);
    },
    [onPageChange],
  );

  return (
    <FunctionalDocShell
      brandIcon={<QuestionCircleOutlined aria-hidden />}
      brandTitle="帮助中心"
      navAriaLabel="帮助目录"
      navGroups={navGroups}
      pageTitle={page.title}
      pageSummary={page.summary}
    >
      <HelpBody body={page.body} onNavigate={handleNavigate} />
      {page.related && page.related.length > 0 ? (
        <footer className="help-center__related">
          <span className="help-center__related-label">相关主题</span>
          <div className="help-center__related-links">
            {page.related.map((rid) => (
              <button
                key={rid}
                type="button"
                className="help-center__related-btn"
                onClick={() => onPageChange(rid)}
              >
                {getHelpPage(rid).title}
              </button>
            ))}
          </div>
        </footer>
      ) : null}
    </FunctionalDocShell>
  );
}
