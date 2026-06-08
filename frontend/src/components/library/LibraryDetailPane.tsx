"use client";

import { useCallback, useEffect, useState } from "react";
import { Spin, message } from "antd";
import { libraryApi } from "@/lib/api";
import type { LibraryItem } from "@/lib/libraryTypes";
import { formatAuthors, formatVenueLine } from "@/lib/libraryTypes";
import {
  formatBibliographicLine,
  formatCitationStats,
} from "@/lib/libraryBibliography";
import {
  openReviewSession,
  resolveAbstractText,
  resolveDisplayTitle,
  uniqueProvenanceSessions,
} from "@/lib/libraryDisplay";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { LibraryTagEditor } from "./LibraryTagEditor";
import { LibraryMetadataEditor } from "./LibraryMetadataEditor";

export type LibraryDetailTab = "abstract" | "fulltext" | "meta" | "pdf" | "reviews";

type RelatedSession = {
  session_id: string;
  session_title: string;
  first_question: string;
  review_ref_index?: number | null;
};

type Props = {
  itemId: string | null;
  listIndex?: number;
  variant?: "page" | "artifact";
  onBack?: () => void;
  activeTab?: LibraryDetailTab;
  onTabChange?: (tab: LibraryDetailTab) => void;
  onItemChange?: (item: LibraryItem) => void;
};

function pickInitialTab(item: LibraryItem, prefer?: LibraryDetailTab): LibraryDetailTab {
  if (prefer === "reviews" && (item.provenance?.length ?? 0) > 0) return "reviews";
  if (prefer === "fulltext" && item.availability?.has_full_text) return "fulltext";
  const abs = resolveAbstractText(item);
  if (abs.text) return "abstract";
  if (item.availability?.has_full_text) return "fulltext";
  if ((item.provenance?.length ?? 0) > 0) return "reviews";
  return "meta";
}

export function LibraryDetailPane({
  itemId,
  listIndex,
  variant = "page",
  onBack,
  activeTab,
  onTabChange,
  onItemChange,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [item, setItem] = useState<LibraryItem | null>(null);
  const [fullText, setFullText] = useState("");
  const [tab, setTab] = useState<LibraryDetailTab>("abstract");
  const [relatedSessions, setRelatedSessions] = useState<RelatedSession[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [tagCatalog, setTagCatalog] = useState<{ name: string; count: number }[]>([]);

  const handleItemUpdated = useCallback(
    (updated: LibraryItem) => {
      setItem(updated);
      onItemChange?.(updated);
      void libraryApi
        .tags()
        .then((res) => setTagCatalog(res.tags || []))
        .catch(() => {});
    },
    [onItemChange],
  );

  const setActiveTab = useCallback(
    (t: LibraryDetailTab) => {
      if (onTabChange) onTabChange(t);
      else setTab(t);
    },
    [onTabChange],
  );

  const currentTab = activeTab ?? tab;

  useEffect(() => {
    void libraryApi
      .tags()
      .then((res) => setTagCatalog(res.tags || []))
      .catch(() => setTagCatalog([]));
  }, [itemId]);

  useEffect(() => {
    if (!itemId) {
      setItem(null);
      setFullText("");
      setRelatedSessions([]);
      return;
    }
    // 关键修复：快速切换 itemId 时，慢响应可能覆盖新选中条目的状态。
    // 用 cancelled 标记 + cleanup 拦截过期请求的 setState。
    let cancelled = false;
    setLoading(true);
    void libraryApi
      .item(itemId)
      .then((res) => {
        if (cancelled) return;
        setItem(res.item);
        setFullText(res.full_text || "");
        if (!activeTab) setTab(pickInitialTab(res.item));
      })
      .catch(() => {
        if (cancelled) return;
        message.error("加载文献详情失败");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemId, activeTab]);

  useEffect(() => {
    if (!itemId || currentTab !== "reviews") return;
    let cancelled = false;
    setReviewsLoading(true);
    void libraryApi
      .relatedSessions(itemId)
      .then((res) => {
        if (cancelled) return;
        setRelatedSessions(res.sessions || []);
      })
      .catch(() => {
        if (cancelled) return;
        // 后端拉取失败时，回退到 item.provenance 中的会话信息，
        // 同时给用户可见的轻量提示（不再用伪造的 item 占位）。
        message.warning("相关综述加载失败，已使用本地缓存");
        if (item) {
          setRelatedSessions(
            uniqueProvenanceSessions(item).map((p) => ({
              session_id: p.session_id,
              session_title: p.session_title,
              first_question: "",
              review_ref_index: p.review_ref_index,
            })),
          );
        } else {
          setRelatedSessions([]);
        }
      })
      .finally(() => {
        if (cancelled) return;
        setReviewsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemId, currentTab, item]);

  const enrich = useCallback(async () => {
    if (!item?.doi) {
      message.info("请先补充 DOI（可在元数据页手工填写）");
      return;
    }
    try {
      const res = await libraryApi.enrich(item.id);
      if (res.item) {
        handleItemUpdated(res.item);
        message.success(
          `被引 ${res.citation_count ?? "—"} · 他引 ${res.references_count ?? "—"}`,
        );
      }
    } catch {
      message.error("元数据补全失败");
    }
  }, [item, handleItemUpdated]);

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
  const displayTitle = resolveDisplayTitle(item);
  const indexLabel = listIndex ?? item.display_index;
  const abstractResolved = resolveAbstractText(item, fullText);
  const hasProv = (item.provenance?.length ?? 0) > 0;
  const isArtifact = variant === "artifact";

  const tabDefs: { key: LibraryDetailTab; label: string; show: boolean }[] = [
    { key: "abstract", label: "摘要", show: true },
    { key: "fulltext", label: "全文", show: Boolean(av.has_full_text) },
    { key: "meta", label: "元数据", show: true },
    { key: "reviews", label: "综述", show: hasProv },
    { key: "pdf", label: "PDF", show: Boolean(av.has_pdf) },
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
          [{indexLabel}] {displayTitle}
        </h2>
      </header>

      <nav className="library-detail__tabs" aria-label="文献详情">
        {tabDefs
          .filter((t) => t.show)
          .map((t) => (
            <button
              key={t.key}
              type="button"
              className={`library-detail__tab${
                currentTab === t.key ? " library-detail__tab--active" : ""
              }`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
      </nav>

      <div className="library-detail__body">
        {currentTab === "abstract" && (
          <div className="library-detail__section">
            <dl className="library-detail__biblio">
              <dt>标题</dt>
              <dd>{displayTitle}</dd>
              <dt>作者</dt>
              <dd>{formatAuthors(item.authors) || "—"}</dd>
              <dt>出处</dt>
              <dd>{formatBibliographicLine(item)}</dd>
              {(item.citation_count != null || item.references_count != null) && (
                <>
                  <dt>引证</dt>
                  <dd>{formatCitationStats(item) || "—"}</dd>
                </>
              )}
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
              {item.publisher && (
                <>
                  <dt>出版社</dt>
                  <dd>{item.publisher}</dd>
                </>
              )}
            </dl>
            <LibraryMetadataEditor item={item} onChange={handleItemUpdated} />
            <h3 className="library-detail__subheading">摘要</h3>
            {abstractResolved.text ? (
              <>
                {abstractResolved.source === "extracted" && (
                  <p className="library-detail__hint">以下摘自抓取正文中的 Abstract 段落。</p>
                )}
                <div className="library-detail__abstract">{abstractResolved.text}</div>
              </>
            ) : av.has_full_text ? (
              <p className="functional-card__empty">
                暂无结构化摘要，
                <button
                  type="button"
                  className="library-detail__inline-link"
                  onClick={() => setActiveTab("fulltext")}
                >
                  查看抓取全文
                </button>
              </p>
            ) : (
              <p className="functional-card__empty">
                暂无摘要。
                {av.fetch_status === "failed" && " 该来源抓取失败。"}
                {av.cite_status === "failed" && " 引用元数据抽取失败。"}
              </p>
            )}
          </div>
        )}

        {currentTab === "fulltext" &&
          (fullText.trim() ? (
            <div
              className="library-detail__markdown meso-markdown"
              dangerouslySetInnerHTML={{
                __html: renderSimpleMarkdown(fullText.slice(0, 120_000)),
              }}
            />
          ) : (
            <p className="functional-card__empty">全文尚未落盘或抓取失败。</p>
          ))}

        {currentTab === "meta" && (
          <dl className="library-detail__meta">
            <dt>被引</dt>
            <dd className="library-detail__meta-row">
              {item.citation_count != null ? (
                <span>{item.citation_count}</span>
              ) : (
                <span className="library-detail__muted">未查询</span>
              )}
              {item.doi && (
                <button type="button" className="library-detail__inline-link" onClick={() => void enrich()}>
                  刷新
                </button>
              )}
            </dd>
            <dt>他引</dt>
            <dd className="library-detail__meta-row">
              {item.references_count != null ? (
                <span>{item.references_count} 条参考文献</span>
              ) : (
                <span className="library-detail__muted">未查询</span>
              )}
            </dd>
            {(item.references_preview?.length ?? 0) > 0 && (
              <>
                <dt>他引预览</dt>
                <dd>
                  <ul className="library-detail__ref-preview">
                    {item.references_preview!.slice(0, 10).map((r, i) => (
                      <li key={`${r.doi || r.title}-${i}`}>
                        {r.title || "Untitled"}
                        {r.year ? ` (${r.year})` : ""}
                      </li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
            <dt>DOI</dt>
            <dd>
              <LibraryMetadataEditor item={item} onChange={handleItemUpdated} />
            </dd>
            <dt>URL</dt>
            <dd>
              <a href={item.url} target="_blank" rel="noreferrer">
                {item.url}
              </a>
            </dd>
            {item.volume && (
              <>
                <dt>卷</dt>
                <dd>{item.volume}</dd>
              </>
            )}
            {item.issue && (
              <>
                <dt>期</dt>
                <dd>{item.issue}</dd>
              </>
            )}
            {item.pages && (
              <>
                <dt>页码</dt>
                <dd>{item.pages}</dd>
              </>
            )}
            <dt>出版社</dt>
            <dd>{item.publisher || "—"}</dd>
            <dt>标签</dt>
            <dd>
              <LibraryTagEditor
                item={item}
                suggestions={tagCatalog}
                onChange={handleItemUpdated}
              />
            </dd>
            <dt>收录综述</dt>
            <dd>
              {hasProv ? (
                <ul className="library-detail__prov">
                  {uniqueProvenanceSessions(item).map((p) => (
                    <li key={p.session_id}>
                      <button
                        type="button"
                        className="library-detail__session-link"
                        onClick={() => openReviewSession(p.session_id)}
                      >
                        {p.session_title}
                      </button>
                      {p.review_ref_index != null ? ` · 文中 [${p.review_ref_index}]` : ""}
                    </li>
                  ))}
                </ul>
              ) : (
                "—"
              )}
            </dd>
            {(item.citations?.apa || item.citations?.acm) && (
              <>
                <dt>引用</dt>
                <dd>
                  {item.citations?.apa && (
                    <pre className="library-detail__cite">{item.citations.apa}</pre>
                  )}
                  {item.citations?.acm && (
                    <pre className="library-detail__cite">{item.citations.acm}</pre>
                  )}
                </dd>
              </>
            )}
          </dl>
        )}

        {currentTab === "reviews" && (
          <div className="library-detail__reviews">
            {reviewsLoading ? (
              <Spin size="small" />
            ) : relatedSessions.length === 0 ? (
              <p className="functional-card__empty">暂无关联综述会话。</p>
            ) : (
              <ul className="library-detail__review-list">
                {relatedSessions.map((s) => (
                  <li key={s.session_id} className="library-detail__review-item">
                    <button
                      type="button"
                      className="library-detail__session-link library-detail__review-title"
                      onClick={() => openReviewSession(s.session_id)}
                    >
                      {s.session_title}
                    </button>
                    {s.review_ref_index != null && (
                      <span className="library-detail__review-ref">
                        文中引用 [{s.review_ref_index}]
                      </span>
                    )}
                    {s.first_question ? (
                      <p className="library-detail__review-question">{s.first_question}</p>
                    ) : (
                      <p className="library-detail__muted">暂无首问记录</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {currentTab === "pdf" && item.full_text?.path?.includes("pdfs/") && (
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
