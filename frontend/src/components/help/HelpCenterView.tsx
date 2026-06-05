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

export function HelpCenterView({ pageId, onPageChange }: Props) {
  const page = getHelpPage(pageId);

  const handleNavigate = useCallback(
    (id: HelpPageId) => {
      onPageChange(id);
    },
    [onPageChange],
  );

  return (
    <div className="help-center-page">
      <header className="help-center-page__header">
        <h1 className="help-center-page__brand">
          <QuestionCircleOutlined aria-hidden />
          帮助中心
        </h1>
      </header>
      <div className="help-center help-center--standalone">
        <nav className="help-center__nav" aria-label="帮助目录">
          {HELP_CATEGORIES.map((cat) => {
            const items = HELP_PAGES.filter((p) => p.category === cat);
            if (!items.length) return null;
            return (
              <div key={cat} className="help-center__nav-group">
                <span className="help-center__nav-cat">{cat}</span>
                <ul className="help-center__nav-list">
                  {items.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        className={`help-center__nav-item${
                          p.id === pageId ? " help-center__nav-item--active" : ""
                        }`}
                        onClick={() => onPageChange(p.id)}
                      >
                        {p.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </nav>
        <div className="help-center__main">
          <header className="help-center__page-header">
            <h2 className="help-center__page-title">{page.title}</h2>
            <p className="help-center__page-summary">{page.summary}</p>
          </header>
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
        </div>
      </div>
    </div>
  );
}
