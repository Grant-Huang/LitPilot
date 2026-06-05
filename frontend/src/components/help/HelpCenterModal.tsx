"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { Modal } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import {
  DEFAULT_HELP_PAGE_ID,
  getHelpPage,
  HELP_CATEGORIES,
  HELP_PAGES,
  type HelpPageId,
} from "@/content/help";
import { renderHelpBodyHtml } from "@/content/help/renderHelpBody";
import { HELP_PAGE_MAP } from "@/content/help/index";

type Props = {
  open: boolean;
  pageId: HelpPageId;
  onClose: () => void;
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
      const target = (event.target as HTMLElement).closest(
        "[data-help-page]",
      ) as HTMLElement | null;
      if (!target) return;
      const id = target.getAttribute("data-help-page");
      if (id && HELP_PAGE_MAP[id as HelpPageId]) {
        event.preventDefault();
        onNavigate(id as HelpPageId);
      }
    },
    [onNavigate],
  );

  if (!html) return null;

  return (
    <div
      className="help-center__body help-center__prose"
      onClick={handleClick}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function HelpCenterModal({ open, pageId, onClose, onPageChange }: Props) {
  const page = getHelpPage(pageId);
  const mainRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 });
  }, [pageId]);

  const handleNavigate = useCallback(
    (id: HelpPageId) => {
      onPageChange(id);
    },
    [onPageChange],
  );

  return (
    <Modal
      title={
        <span className="help-center__title">
          <QuestionCircleOutlined aria-hidden />
          帮助中心
        </span>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={920}
      className="help-center-modal"
      destroyOnHidden
      styles={{
        body: {
          padding: 0,
          overflow: "hidden",
          maxHeight: "min(72vh, 640px)",
        },
      }}
    >
      <div className="help-center">
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
        <div className="help-center__main" ref={mainRef}>
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
    </Modal>
  );
}

export { DEFAULT_HELP_PAGE_ID };
export type { HelpPageId };
