"use client";

import { useMemo, useState } from "react";
import {
  buildSearchProgressTree,
  subtopicDisplayTitle,
  subtopicStatusLabel,
  type SubtopicProgressNode,
  type SourceNode,
  type FilterDetailItem,
} from "@/lib/searchProgressTree";

type Props = {
  extensions: Array<{ name: string; data: Record<string, unknown> }>;
  subTopics?: Array<{ id?: string; title?: string; search_query?: string }>;
  streaming?: boolean;
};

function phaseMarker(status: string) {
  if (status === "running") return <span className="litpilot-log-line__spinner" />;
  if (status === "error") return "×";
  if (status === "done") return "✓";
  return "·";
}

function SourceRow({ source }: { source: SourceNode }) {
  const detail = source.failed
    ? "失败"
    : "命中 " + source.hits + " 篇";
  return (
    <li className={`litpilot-search-source litpilot-search-source--${source.status}`}>
      <span className="litpilot-search-source__marker" aria-hidden="true">
        {phaseMarker(source.status)}
      </span>
      <div className="litpilot-search-source__body">
        <span className="litpilot-search-source__label">{source.label}</span>
        <span className="litpilot-search-source__status">{detail}</span>
      </div>
    </li>
  );
}

function FilterDetailRow({ item }: { item: FilterDetailItem }) {
  const label = item.keep
    ? "保留"
    : "剔除 [" + (item.score ?? "?") + "]";
  const reason = item.keep ? "" : item.reason ?? "";
  const title = item.title || "(无标题)";
  const cls = item.keep ? "done" : "error";
  return (
    <li className={`litpilot-search-source litpilot-search-source--${cls}`}>
      <span className="litpilot-search-source__marker" aria-hidden="true">
        {item.keep ? "●" : "○"}
      </span>
      <div className="litpilot-search-source__body">
        <span className="litpilot-search-source__label">{title}</span>
        <span className="litpilot-search-source__status">
          {label}{reason ? " · " + reason.slice(0, 60) : ""}
        </span>
      </div>
    </li>
  );
}

function SubtopicBlock({
  node,
  defaultOpen,
}: {
  node: SubtopicProgressNode;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const title = subtopicDisplayTitle(node);
  const status = subtopicStatusLabel(node);

  return (
    <div className={`litpilot-search-topic litpilot-search-topic--${node.search.status === "running" || node.filter.status === "running" ? "running" : "done"}`}>
      <button
        type="button"
        className="litpilot-search-topic__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="litpilot-search-topic__marker" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="litpilot-search-topic__title">{title}</span>
        <span className="litpilot-search-topic__status">{status}</span>
      </button>
      {open ? (
        <ul className="litpilot-search-topic__sources">
          {/* Search phase: per-source details */}
          {node.search.status !== "pending" ? (
            <li key="search" className="litpilot-search-source litpilot-search-source--done">
              <button
                type="button"
                className="litpilot-search-source__head"
                onClick={() => setSourcesOpen((v) => !v)}
                aria-expanded={sourcesOpen}
              >
                <span className="litpilot-search-source__marker" aria-hidden="true">
                  {sourcesOpen ? "▾" : node.search.status === "running" ? <span className="litpilot-log-line__spinner" /> : "▸"}
                </span>
                <span className="litpilot-search-source__label">检索</span>
                <span className="litpilot-search-source__status">
                  {node.search.detail ?? (node.search.status === "running" ? "进行中…" : "完成")}
                </span>
              </button>
              {sourcesOpen && node.sources.length > 0 ? (
                <ul className="litpilot-search-topic__sub-items">
                  {node.sources.map((src, i) => (
                    <SourceRow key={`${src.label}-${i}`} source={src} />
                  ))}
                </ul>
              ) : null}
            </li>
          ) : null}

          {/* Filter phase: kept/rejected details */}
          {node.filter.status !== "pending" ? (
            <li key="filter" className={`litpilot-search-source litpilot-search-source--${node.filter.status}`}>
              <button
                type="button"
                className="litpilot-search-source__head"
                onClick={() => setFilterOpen((v) => !v)}
                aria-expanded={filterOpen}
              >
                <span className="litpilot-search-source__marker" aria-hidden="true">
                  {filterOpen ? "▾" : node.filter.status === "running" ? <span className="litpilot-log-line__spinner" /> : "▸"}
                </span>
                <span className="litpilot-search-source__label">过滤</span>
                <span className="litpilot-search-source__status">
                  {node.filter.detail ?? (node.filter.status === "running" ? "进行中…" : "完成")}
                </span>
              </button>
              {filterOpen && node.filterDetails.length > 0 ? (
                <ul className="litpilot-search-topic__sub-items">
                  {node.filterDetails.map((item, i) => (
                    <FilterDetailRow key={`${item.title}-${i}`} item={item} />
                  ))}
                </ul>
              ) : null}
            </li>
          ) : null}
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
    const phases = [st.search, st.filter];
    return phases.some((p) => p.status === "running");
  });
  const aggregatePending =
    streaming && !summary.allDone && summary.completedSubtopics < summary.totalSubtopics;
  const aggregateLabel = summary.allDone
    ? "检索完成 · " + summary.completedSubtopics + "/" + summary.totalSubtopics + " 子主题"
    : aggregatePending
      ? "检索中 · " + summary.completedSubtopics + "/" + summary.totalSubtopics + " 子主题"
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
