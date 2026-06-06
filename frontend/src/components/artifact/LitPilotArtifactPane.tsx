"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArtifactPanel } from "@meso.ai/ui";
import type { StreamState } from "@meso.ai/ui";
import { downloadTextFile } from "@/lib/buildArtifactStream";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { LITERATURE_OUTLINE_LANG, findOutlineArtifact } from "@/lib/literatureOutline";
import { LiteratureOutlineView } from "@/components/artifact/LiteratureOutlineView";
import { LiteratureArtifactView } from "@/components/library/LiteratureArtifactView";
import { findItemByDisplayIndex } from "@/lib/resolveLibraryItem";
import { reviewMarkdownForDisplay } from "@/lib/reviewDisplay";
import type { LibraryItem } from "@/lib/libraryTypes";
import { sessionsApi } from "@/lib/api";

type MainTab = "outline" | "review" | "literature";
type ReviewMode = "render" | "source";

type ReviewVersion = {
  id: string;
  filename: string;
  created_at?: string;
};

type Props = {
  streamState: StreamState;
  reviewFilename?: string;
  libraryItems?: LibraryItem[];
  selectedLibraryId?: string | null;
  onSelectLibraryId?: (id: string | null) => void;
  activeSessionId?: string | null;
  onLiteratureDetailOpen?: (open: boolean) => void;
};

function extractReviewRefIndices(text: string): number[] {
  const seen = new Set<number>();
  const out: number[] = [];
  const re = /\[(\d{1,3})\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const n = parseInt(m[1], 10);
    if (!seen.has(n)) {
      seen.add(n);
      out.push(n);
    }
  }
  return out.sort((a, b) => a - b);
}

function listReviewArtifacts(streamState: StreamState) {
  const items: Array<{ id: string; art: StreamState["artifacts"][string] }> = [];
  for (const id of streamState.artifactOrder) {
    const art = streamState.artifacts[id];
    if (!art || art.lang === LITERATURE_OUTLINE_LANG) continue;
    const lang = art.lang.toLowerCase();
    if (
      lang === "markdown" ||
      lang.endsWith("/markdown") ||
      lang.endsWith("+markdown")
    ) {
      items.push({ id, art });
    }
  }
  return items;
}

export function LitPilotArtifactPane({
  streamState,
  reviewFilename = "review-latest.md",
  libraryItems = [],
  selectedLibraryId = null,
  onSelectLibraryId,
  activeSessionId,
  onLiteratureDetailOpen,
}: Props) {
  const outlineArtifact = useMemo(
    () => findOutlineArtifact(streamState.artifacts, streamState.artifactOrder),
    [streamState.artifacts, streamState.artifactOrder],
  );

  const reviewArtifacts = useMemo(
    () => listReviewArtifacts(streamState),
    [streamState.artifacts, streamState.artifactOrder],
  );

  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [savedVersions, setSavedVersions] = useState<ReviewVersion[]>([]);
  const [savedReviewContent, setSavedReviewContent] = useState<string | null>(null);

  const reviewArtifact = useMemo(() => {
    if (selectedReviewId) {
      const hit = reviewArtifacts.find((r) => r.id === selectedReviewId);
      if (hit) return hit;
    }
    return reviewArtifacts[reviewArtifacts.length - 1] ?? null;
  }, [reviewArtifacts, selectedReviewId]);

  const selectedSavedVersion = useMemo(
    () => savedVersions.find((v) => v.id === selectedReviewId) ?? null,
    [savedVersions, selectedReviewId],
  );

  const showOutline = Boolean(outlineArtifact);
  const activeReviewContent =
    selectedSavedVersion && savedReviewContent != null
      ? savedReviewContent
      : (reviewArtifact?.art.content ?? "");
  const showReview = Boolean(activeReviewContent.trim());
  const showLiterature = libraryItems.length > 0;

  const [mainTab, setMainTab] = useState<MainTab>("review");
  const [reviewMode, setReviewMode] = useState<ReviewMode>("render");
  const reviewAutoOpenedRef = useRef(false);
  const literatureAutoOpenedRef = useRef(false);
  const outlineAutoOpenedRef = useRef(false);

  useEffect(() => {
    if (!activeSessionId) {
      setSavedVersions([]);
      return;
    }
    void sessionsApi.get(activeSessionId).then((meta) => {
      const versions = (meta?.review_versions ?? []) as ReviewVersion[];
      setSavedVersions(Array.isArray(versions) ? versions : []);
    }).catch(() => setSavedVersions([]));
  }, [activeSessionId, reviewArtifacts.length]);

  useEffect(() => {
    if (!activeSessionId || !selectedSavedVersion) {
      setSavedReviewContent(null);
      return;
    }
    void sessionsApi
      .reviewVersion(activeSessionId, selectedSavedVersion.filename)
      .then((row) => setSavedReviewContent(row.content))
      .catch(() => setSavedReviewContent(null));
  }, [activeSessionId, selectedSavedVersion]);

  useEffect(() => {
    reviewAutoOpenedRef.current = false;
    literatureAutoOpenedRef.current = false;
    outlineAutoOpenedRef.current = false;
  }, [reviewArtifact?.id, outlineArtifact?.id]);

  useEffect(() => {
    if (showReview && !reviewArtifact?.art.done) {
      setMainTab("review");
    }
  }, [showReview, reviewArtifact?.art.done]);

  useEffect(() => {
    if (showOutline && outlineArtifact?.done && !outlineAutoOpenedRef.current) {
      setMainTab("outline");
      outlineAutoOpenedRef.current = true;
    }
  }, [showOutline, outlineArtifact?.done, outlineArtifact?.id]);

  useEffect(() => {
    const reviewDone = showReview && Boolean(reviewArtifact?.art.done);
    if (!reviewDone) return;
    const artifactLang = reviewArtifact?.art.lang.toLowerCase() ?? "";
    const isMatrix =
      artifactLang.includes("matrix") ||
      Boolean(reviewArtifact?.id.includes("matrix"));
    if (isMatrix) {
      setMainTab("review");
      reviewAutoOpenedRef.current = true;
      return;
    }
    if (showLiterature && !literatureAutoOpenedRef.current) {
      setMainTab("literature");
      literatureAutoOpenedRef.current = true;
      if (!selectedLibraryId) {
        const reviewContent = reviewArtifact?.art.content ?? "";
        const firstRef = extractReviewRefIndices(reviewContent)[0];
        const byRef =
          firstRef != null
            ? findItemByDisplayIndex(libraryItems, firstRef)
            : undefined;
        const pick = byRef ?? libraryItems[0];
        if (pick) {
          onSelectLibraryId?.(pick.id);
          onLiteratureDetailOpen?.(true);
        }
      }
      return;
    }
    if (!showLiterature && !reviewAutoOpenedRef.current) {
      setMainTab("review");
      reviewAutoOpenedRef.current = true;
    }
  }, [
    showReview,
    reviewArtifact?.art.done,
    reviewArtifact?.art.content,
    reviewArtifact?.art.lang,
    reviewArtifact?.id,
    showLiterature,
    libraryItems,
    selectedLibraryId,
    onSelectLibraryId,
    onLiteratureDetailOpen,
  ]);

  const reviewLang = reviewArtifact?.art.lang.toLowerCase() ?? "markdown";
  const isMarkdownReview =
    reviewLang === "markdown" ||
    reviewLang.endsWith("/markdown") ||
    reviewLang.endsWith("+markdown");
  const isMatrixArtifact =
    reviewLang.includes("matrix") ||
    Boolean(reviewArtifact?.id.includes("matrix"));
  const artifactLabel = isMatrixArtifact ? "矩阵" : "综述";
  const artifactFilename = isMatrixArtifact
    ? "matrix-latest.md"
    : reviewFilename;
  const reviewContent = activeReviewContent;
  const reviewStreaming =
    reviewArtifact && !selectedSavedVersion ? !reviewArtifact.art.done : false;
  const reviewRefIndices = extractReviewRefIndices(reviewContent);

  const displayReview = useMemo(
    () =>
      reviewMarkdownForDisplay(reviewContent, {
        collapseReferences: Boolean(
          !isMatrixArtifact && showLiterature && reviewArtifact?.art.done,
        ),
      }),
    [reviewContent, isMatrixArtifact, showLiterature, reviewArtifact?.art.done],
  );

  if (!showOutline && !showReview && !showLiterature) {
    return (
      <p className="litpilot-artifact-pane__empty">
        执行文献综述后，可在此查看章节大纲、生成的综述与文献库。
      </p>
    );
  }

  const jumpToRef = (index: number) => {
    const hit = findItemByDisplayIndex(libraryItems, index);
    if (hit) {
      setMainTab("literature");
      onSelectLibraryId?.(hit.id);
      onLiteratureDetailOpen?.(true);
    }
  };

  const handleDownload = (content: string) => {
    downloadTextFile(artifactFilename, content);
  };

  const literatureDetailOpen =
    mainTab === "literature" && Boolean(selectedLibraryId);

  const versionOptions = [
    ...reviewArtifacts.map((r, idx) => ({
      id: r.id,
      label: `流式 v${idx + 1}${r.art.done ? "" : " · 生成中"}`,
    })),
    ...savedVersions.map((v, idx) => ({
      id: v.id,
      label: `已保存 v${savedVersions.length - idx}`,
    })),
  ];

  return (
    <div
      className={`litpilot-artifact-pane${
        literatureDetailOpen ? " litpilot-artifact-pane--literature-detail" : ""
      }`}
    >
      <div className="litpilot-artifact-pane__toolbar">
        <div className="litpilot-artifact-pane__tabs" role="tablist">
          {showOutline && (
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "outline"}
              className={`litpilot-artifact-pane__tab${
                mainTab === "outline" ? " litpilot-artifact-pane__tab--active" : ""
              }`}
              onClick={() => setMainTab("outline")}
            >
              大纲
            </button>
          )}
          {showReview && (
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "review"}
              className={`litpilot-artifact-pane__tab${
                mainTab === "review"
                  ? " litpilot-artifact-pane__tab--active"
                  : ""
              }`}
              onClick={() => setMainTab("review")}
            >
              {artifactLabel}
            </button>
          )}
          {showLiterature && (
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "literature"}
              className={`litpilot-artifact-pane__tab${
                mainTab === "literature"
                  ? " litpilot-artifact-pane__tab--active"
                  : ""
              }`}
              onClick={() => setMainTab("literature")}
            >
              文献
            </button>
          )}
        </div>
        {mainTab === "review" && showReview && isMarkdownReview && (
          <div className="litpilot-artifact-pane__subtabs">
            <button
              type="button"
              className={`litpilot-artifact-pane__subtab${
                reviewMode === "render"
                  ? " litpilot-artifact-pane__subtab--active"
                  : ""
              }`}
              onClick={() => setReviewMode("render")}
            >
              渲染
            </button>
            <button
              type="button"
              className={`litpilot-artifact-pane__subtab${
                reviewMode === "source"
                  ? " litpilot-artifact-pane__subtab--active"
                  : ""
              }`}
              onClick={() => setReviewMode("source")}
            >
              原文
            </button>
          </div>
        )}
      </div>

      {mainTab === "review" && showReview && (
        <>
          {versionOptions.length > 1 ? (
            <div className="litpilot-artifact-pane__version-row">
              <label htmlFor="review-version">版本</label>
              <select
                id="review-version"
                className="input"
                value={selectedReviewId ?? reviewArtifact?.id ?? ""}
                onChange={(e) => setSelectedReviewId(e.target.value || null)}
              >
                {versionOptions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <p className="litpilot-artifact-pane__file-hint">
            文件：<code>{artifactFilename}</code>
          </p>
          {reviewRefIndices.length > 0 && showLiterature && (
            <div className="litpilot-artifact-pane__ref-jump">
              <span>参考文献：</span>
              {reviewRefIndices.map((n) => (
                <button
                  key={n}
                  type="button"
                  className="litpilot-artifact-pane__ref-btn"
                  onClick={() => jumpToRef(n)}
                >
                  [{n}]
                </button>
              ))}
            </div>
          )}
        </>
      )}

      <div className="litpilot-artifact-pane__body">
        {mainTab === "outline" && showOutline && outlineArtifact && (
          <LiteratureOutlineView
            outline={outlineArtifact.outline}
            streaming={!outlineArtifact.done}
          />
        )}
        {mainTab === "review" && showReview && isMarkdownReview && (
          <>
            {reviewMode === "render" ? (
              <ArtifactPanel
                type="markdown"
                content={displayReview}
                language="markdown"
                streaming={reviewStreaming}
                renderMarkdown={renderSimpleMarkdown}
                onDownload={() => handleDownload(displayReview)}
              />
            ) : (
              <ArtifactPanel
                type="code"
                content={displayReview}
                language="markdown"
                streaming={reviewStreaming}
                onDownload={() => handleDownload(displayReview)}
              />
            )}
          </>
        )}
        {mainTab === "literature" && showLiterature && (
          <LiteratureArtifactView
            items={libraryItems}
            selectedId={selectedLibraryId}
            onSelectId={onSelectLibraryId ?? (() => {})}
            activeSessionId={activeSessionId}
            onLiteratureDetailOpen={onLiteratureDetailOpen}
          />
        )}
      </div>
    </div>
  );
}
