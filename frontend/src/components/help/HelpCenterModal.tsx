"use client";

import { useCallback, useMemo } from "react";
import { Modal } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import {
  DEFAULT_HELP_PAGE_ID,
  getHelpPage,
  HELP_CATEGORIES,
  HELP_PAGES,
  type HelpPageId,
} from "@/content/help";
import { renderHelpMarkdownChunk, splitHelpBody } from "@/content/help/renderHelpBody";
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
  const parts = useMemo(() => splitHelpBody(body), [body]);

  return (
    <div className="help-center__body">
      {parts.map((part, idx) => {
        if (part.kind === "link") {
          if (!HELP_PAGE_MAP[part.id]) {
            return <span key={idx}>{part.label}</span>;
          }
          return (
            <button
              key={idx}
              type="button"
              className="help-center__inline-link"
              onClick={() => onNavigate(part.id)}
            >
              {part.label}
            </button>
          );
        }
        const html = renderHelpMarkdownChunk(part.text);
        if (!html) return null;
        return (
          <div
            key={idx}
            className="help-center__md"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        );
      })}
    </div>
  );
}

export function HelpCenterModal({ open, pageId, onClose, onPageChange }: Props) {
  const page = getHelpPage(pageId);

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
    </Modal>
  );
}

export { DEFAULT_HELP_PAGE_ID };
export type { HelpPageId };
