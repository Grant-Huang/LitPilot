"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArtifactPanel } from "@meso.ai/ui";
import type { StreamState } from "@meso.ai/ui";
import { WorkflowArtifactPanel } from "@/components/workflow/WorkflowArtifactPanel";
import { downloadTextFile } from "@/lib/buildArtifactStream";
import { LITERATURE_PLAN_GRAPH } from "@/lib/literaturePlanGraph";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import {
  findWorkflowArtifact,
  WORKFLOW_GRAPH_LANG,
} from "@/lib/workflowGraph";
import { graphForDagDisplay } from "@/lib/dagDisplayGraph";
import { mergeWorkflowRunsIntoGraph } from "@/lib/workflowGraphLive";
import { workflowRunsFromStream } from "@/lib/workflowRuns";
import { LiteratureArtifactView } from "@/components/library/LiteratureArtifactView";
import { findItemByDisplayIndex } from "@/lib/resolveLibraryItem";
import { reviewMarkdownForDisplay } from "@/lib/reviewDisplay";
import type { LibraryItem } from "@/lib/libraryTypes";

type MainTab = "dag" | "review" | "literature";
type ReviewMode = "render" | "source";

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

export function LitPilotArtifactPane({
  streamState,
  reviewFilename = "review-latest.md",
  libraryItems = [],
  selectedLibraryId = null,
  onSelectLibraryId,
  activeSessionId,
  onLiteratureDetailOpen,
}: Props) {
  const workflowRuns = workflowRunsFromStream(streamState);
  const workflow = findWorkflowArtifact(
    streamState.artifacts,
    streamState.artifactOrder,
  );

  const reviewArtifact = useMemo(() => {
    for (let i = streamState.artifactOrder.length - 1; i >= 0; i -= 1) {
      const id = streamState.artifactOrder[i];
      const art = streamState.artifacts[id];
      if (!art || art.lang === WORKFLOW_GRAPH_LANG) continue;
      const lang = art.lang.toLowerCase();
      if (lang === "markdown" || lang.endsWith("/markdown")) {
        return { id, art };
      }
    }
    return null;
  }, [streamState.artifacts, streamState.artifactOrder]);

  const runId =
    workflow?.id ??
    workflowRuns[workflowRuns.length - 1]?.run_id ??
    "literature-agent";

  const baseGraph = workflow?.graph ?? LITERATURE_PLAN_GRAPH;
  const liveGraph = graphForDagDisplay(
    mergeWorkflowRunsIntoGraph(baseGraph, runId, workflowRuns),
  );

  const showDag = workflowRuns.length > 0 || Boolean(workflow);
  const showReview = Boolean(reviewArtifact?.art.content?.trim());
  const showLiterature = libraryItems.length > 0;

  const [mainTab, setMainTab] = useState<MainTab>("dag");
  const [reviewMode, setReviewMode] = useState<ReviewMode>("render");
  const reviewAutoOpenedRef = useRef(false);
  const literatureAutoOpenedRef = useRef(false);

  useEffect(() => {
    reviewAutoOpenedRef.current = false;
    literatureAutoOpenedRef.current = false;
  }, [reviewArtifact?.id]);

  useEffect(() => {
    if (showReview && !showDag && !reviewArtifact?.art.done) {
      setMainTab("review");
    }
  }, [showReview, showDag, reviewArtifact?.art.done]);

  /** 综述完成后默认展开文献 Tab（文献库晚于 SSE 到达时也会补切一次） */
  useEffect(() => {
    const reviewDone = showReview && Boolean(reviewArtifact?.art.done);
    if (!reviewDone) return;

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
    reviewArtifact?.id,
    showLiterature,
    libraryItems,
    selectedLibraryId,
    onSelectLibraryId,
  ]);

  const reviewLang = reviewArtifact?.art.lang.toLowerCase() ?? "markdown";
  const isMarkdownReview =
    reviewLang === "markdown" || reviewLang.endsWith("/markdown");
  const reviewContent = reviewArtifact?.art.content ?? "";
  const reviewStreaming = reviewArtifact ? !reviewArtifact.art.done : false;
  const reviewRefIndices = extractReviewRefIndices(reviewContent);

  const displayReview = useMemo(
    () =>
      reviewMarkdownForDisplay(reviewContent, {
        collapseReferences: Boolean(showLiterature && reviewArtifact?.art.done),
      }),
    [reviewContent, showLiterature, reviewArtifact?.art.done],
  );

  if (!showDag && !showReview && !showLiterature) {
    return (
      <p className="litpilot-artifact-pane__empty">
        执行文献综述后，可在此切换查看工作流 DAG 与生成的综述文件。
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
    downloadTextFile(reviewFilename, content);
  };

  const literatureDetailOpen =
    mainTab === "literature" && Boolean(selectedLibraryId);

  return (
    <div
      className={`litpilot-artifact-pane${
        literatureDetailOpen ? " litpilot-artifact-pane--literature-detail" : ""
      }`}
    >
      <div className="litpilot-artifact-pane__toolbar">
        <div className="litpilot-artifact-pane__tabs" role="tablist">
          {showDag && (
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "dag"}
              className={`litpilot-artifact-pane__tab${
                mainTab === "dag" ? " litpilot-artifact-pane__tab--active" : ""
              }`}
              onClick={() => setMainTab("dag")}
            >
              DAG
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
              综述
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
          <p className="litpilot-artifact-pane__file-hint">
            文件：<code>{reviewFilename}</code>
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
        {mainTab === "dag" && showDag && (
          <WorkflowArtifactPanel
            graph={liveGraph}
            workflowRuns={workflowRuns}
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
                onDownload={handleDownload}
              />
            ) : (
              <ArtifactPanel
                type="code"
                content={displayReview}
                language="markdown"
                streaming={reviewStreaming}
                onDownload={handleDownload}
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
