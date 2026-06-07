"use client";

import { useMemo, useState } from "react";
import {
  buildSearchProgressTree,
  subtopicDisplayTitle,
  subtopicStatusLabel,
  type SubtopicProgressNode,
} from "@/lib/searchProgressTree";

type Props = {
  extensions: Array<{ name: string; data: Record<string, unknown> }>;
  subTopics?: Array<{ id?: string; title?: string; search_query?: string }>;
  streaming?: boolean;
};

function phaseMarker(status: SubtopicProgressNode["search"]["status"]) {
  if (status === "running") return <span className="litpilot-log-line__spinner" />;
  if (status === "error") return "×";
  if (status === "done") return "✓";
  return "·";
}

function SubtopicBlock({
  node,
  defaultOpen,
}: {
  node: SubtopicProgressNode;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const title = subtopicDisplayTitle(node);
  const status = subtopicStatusLabel(node);
  const phases = [node.search, node.filter, node.fetch];
  const pending = phases.some((p) => p.status === "running");

  return (
    <div className={`litpilot-search-topic litpilot-search-topic--${pending ? "running" : "done"}`}>
      <button
        type="button"
        className="litpilot-search-topic__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="litpilot-search-topic__marker" aria-hidden="true">
          {pending ? (
            <span className="litpilot-log-line__spinner" />
          ) : open ? (
            "▾"
          ) : (
            "▸"
          )}
        </span>
        <span className="litpilot-search-topic__title">{title}</span>
        <span className="litpilot-search-topic__status">{status}</span>
      </button>
      {open ? (
        <ul className="litpilot-search-topic__sources">
          {phases.map((phase) => (
            <li
              key={phase.label}
              className={`litpilot-search-source litpilot-search-source--${phase.status}`}
            >
              <span className="litpilot-search-source__marker" aria-hidden="true">
                {phaseMarker(phase.status)}
              </span>
              <div className="litpilot-search-source__body">
                <span className="litpilot-search-source__label">{phase.label}</span>
                <span className="litpilot-search-source__status">
                  {phase.detail ?? (phase.status === "pending" ? "待开始" : phase.status === "running" ? "进行中…" : "完成")}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function SearchProgressView({
  extensions,
  subTopics,
  streaming = false,
}: Props) {
  const summary = useMemo(
    () =>
      buildSearchProgressTree(
        extensions,
        subTopics?.map((st) => ({
          id: String(st.id ?? ""),
          title: String(st.title ?? ""),
          search_query: String(st.search_query ?? ""),
        })),
      ),
    [extensions, subTopics],
  );

  if (!summary.subtopics.length) return null;

  const runningIdx = summary.subtopics.findIndex((st) => {
    const phases = [st.search, st.filter, st.fetch];
    return phases.some((p) => p.status === "running");
  });
  const aggregatePending =
    streaming && !summary.allDone && summary.completedSubtopics < summary.totalSubtopics;
  const aggregateLabel = summary.allDone
    ? `检索完成 · ${summary.completedSubtopics}/${summary.totalSubtopics} 子主题`
    : aggregatePending
      ? `检索中 · ${summary.completedSubtopics}/${summary.totalSubtopics} 子主题`
      : null;

  return (
    <div className="litpilot-search-progress" role="list">
      {aggregateLabel ? (
        <p className="litpilot-search-progress__aggregate">{aggregateLabel}</p>
      ) : null}
      {summary.subtopics.map((node, i) => (
        <SubtopicBlock
          key={node.id}
          node={node}
          defaultOpen={
            runningIdx === i ||
            (runningIdx < 0 && i === summary.subtopics.length - 1 && streaming)
          }
        />
      ))}
    </div>
  );
}
