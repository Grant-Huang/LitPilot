"use client";

import { useCallback, useEffect, useState } from "react";
import { Dropdown, Spin, message } from "antd";
import type { MenuProps } from "antd";
import { libraryApi } from "@/lib/api";
import type { LibraryItem } from "@/lib/libraryTypes";
import { formatAuthors, formatVenueLine } from "@/lib/libraryTypes";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";

type DetailTab = "abstract" | "fulltext" | "meta" | "pdf";

type Props = {
  itemId: string | null;
  variant?: "page" | "artifact";
  onBack?: () => void;
  initialTab?: DetailTab;
  onStarChange?: (item: LibraryItem) => void;
};

function pickInitialTab(item: LibraryItem, prefer?: DetailTab): DetailTab {
  if (prefer === "fulltext" && item.availability?.has_full_text) return "fulltext";
  if (item.abstract?.trim()) return "abstract";
  if (item.availability?.has_full_text) return "fulltext";
  return "abstract";
}

export function LibraryDetailPane({
  itemId,
  variant = "page",
  onBack,
  initialTab,
  onStarChange,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [item, setItem] = useState<LibraryItem | null>(null);
  const [fullText, setFullText] = useState("");
  const [tab, setTab] = useState<DetailTab>("abstract");

  useEffect(() => {
    if (!itemId) {
      setItem(null);
      setFullText("");
      return;
    }
    setLoading(true);
    void libraryApi
      .item(itemId)
      .then((res) => {
        setItem(res.item);
        setFullText(res.full_text || "");
        setTab(pickInitialTab(res.item, initialTab));
      })
      .catch(() => message.error("加载文献详情失败"))
      .finally(() => setLoading(false));
  }, [itemId, initialTab]);

  const toggleStar = useCallback(async () => {
    if (!item) return;
    try {
      const res = await libraryApi.star(item.id, !item.starred);
      setItem(res.item);
      onStarChange?.(res.item);
    } catch {
      message.error("更新收藏失败");
    }
  }, [item, onStarChange]);

  const enrich = useCallback(async () => {
    if (!item?.doi) {
      message.info("该文献无 DOI，暂无法查询被引数");
      return;
    }
    try {
      const res = await libraryApi.enrich(item.id);
      if (res.item) {
        setItem(res.item);
        message.success(`被引数：${res.citation_count ?? "—"}`);
      }
    } catch {
      message.error("元数据补全失败");
    }
  }, [item]);

  if (!itemId) {
    return (
      <div className="library-detail library-detail--empty">
        <p>
          {variant === "artifact"
            ? "点击列表中的文献查看摘要与全文。"
            : "选择左侧文献查看摘要、全文与元数据。"}
        </p>
      </div>
    );
  }

  if (loading || !item) {
    return (
      <div className="library-detail library-detail--loading">
        <Spin />
      </div>
    );
  }

  const av = item.availability || {};
  const apa = item.citations?.apa || item.citations?.acm || "";
  const isArtifact = variant === "artifact";

  const menuItems: MenuProps["items"] = [
    {
      key: "star",
      label: item.starred ? "取消收藏" : "收藏",
      onClick: () => void toggleStar(),
    },
    {
      key: "enrich",
      label: "补全被引数",
      onClick: () => void enrich(),
    },
    ...(apa
      ? [
          {
            key: "copy",
            label: "复制引用",
            onClick: () => {
              void navigator.clipboard.writeText(apa);
              message.success("已复制引用");
            },
          },
        ]
      : []),
  ];

  return (
    <div
      className={`library-detail${isArtifact ? " library-detail--artifact" : ""}`}
    >
      <header className="library-detail__header">
        {isArtifact && onBack && (
          <button
            type="button"
            className="library-detail__back"
            onClick={onBack}
            aria-label="返回列表"
          >
            ← 列表
          </button>
        )}
        <h2 className="library-detail__title">
          [{item.display_index}] {item.title}
        </h2>
        <div className="library-detail__actions">
          <Dropdown menu={{ items: menuItems }} trigger={["click"]}>
            <button type="button" className="btn-ghost">
              更多操作 ▾
            </button>
          </Dropdown>
        </div>
      </header>

      <nav className="library-detail__tabs" aria-label="文献详情">
        {(["abstract", "fulltext", "meta", "pdf"] as DetailTab[]).map((t) => {
          if (t === "fulltext" && !av.has_full_text) return null;
          if (t === "pdf" && !av.has_pdf) return null;
          const labels: Record<DetailTab, string> = {
            abstract: "摘要",
            fulltext: "全文",
            meta: "元数据",
            pdf: "PDF",
          };
          return (
            <button
              key={t}
              type="button"
              className={`library-detail__tab${tab === t ? " library-detail__tab--active" : ""}`}
              onClick={() => setTab(t)}
            >
              {labels[t]}
            </button>
          );
        })}
      </nav>

      <div className="library-detail__body">
        {tab === "abstract" && (
          <div className="library-detail__section">
            <p className="library-detail__authors">{formatAuthors(item.authors)}</p>
            <p className="library-detail__venue">{formatVenueLine(item)}</p>
            {item.abstract ? (
              <div className="library-detail__abstract">{item.abstract}</div>
            ) : av.has_full_text ? (
              <p className="functional-card__empty">
                暂无结构化摘要，
                <button
                  type="button"
                  className="library-detail__inline-link"
                  onClick={() => setTab("fulltext")}
                >
                  查看抓取全文
                </button>
              </p>
            ) : (
              <p className="functional-card__empty">
                暂无摘要。
                {av.fetch_status === "failed" && " 该来源抓取失败，可在文献库重试。"}
                {av.cite_status === "failed" && " 引用元数据抽取失败。"}
              </p>
            )}
          </div>
        )}
        {tab === "fulltext" && (
          fullText.trim() ? (
            <div
              className="library-detail__markdown meso-markdown"
              dangerouslySetInnerHTML={{
                __html: renderSimpleMarkdown(fullText.slice(0, 120_000)),
              }}
            />
          ) : (
            <p className="functional-card__empty">全文尚未落盘或抓取失败。</p>
          )
        )}
        {tab === "meta" && (
          <dl className="library-detail__meta">
            <dt>URL</dt>
            <dd>
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.url}
              </a>
            </dd>
            {item.doi && (
              <>
                <dt>DOI</dt>
                <dd>
                  <a
                    href={`https://doi.org/${item.doi}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {item.doi}
                  </a>
                </dd>
              </>
            )}
            <dt>出版社</dt>
            <dd>{item.publisher || "—"}</dd>
            <dt>收录综述</dt>
            <dd>
              {(item.provenance || []).length ? (
                <ul className="library-detail__prov">
                  {(item.provenance || []).map((p, i) => (
                    <li key={`${p.session_id}-${p.role}-${i}`}>
                      {p.session_title || p.session_id} · {p.role}
                      {p.review_ref_index != null ? ` · [${p.review_ref_index}]` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                "—"
              )}
            </dd>
            {apa && (
              <>
                <dt>引用</dt>
                <dd>
                  <pre className="library-detail__cite">{apa}</pre>
                </dd>
              </>
            )}
          </dl>
        )}
        {tab === "pdf" && item.full_text?.path?.includes("pdfs/") && (
          <iframe
            title="PDF 预览"
            className="library-detail__pdf"
            src={`/api/library/pdfs/${encodeURIComponent(item.full_text.path.replace(/^pdfs\//, ""))}`}
          />
        )}
      </div>
    </div>
  );
}
