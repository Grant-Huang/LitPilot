"use client";

import { useMemo, useState } from "react";
import {
  buildSearchProgressTree,
  subtopicDisplayTitle,
  subtopicStatusLabel,
  subtopicDone,
  type SubtopicProgressNode,
  type SourceNode,
  type FilterDetailItem,
} from "@/lib/searchProgressTree";
import { StatusIcon } from "./StatusIcon";

type SubTopicDef = { id?: string; title?: string; search_query?: string };

type Props = {
  extensions: Array<{ name: string; data: Record<string, unknown> }>;
  subTopics?: SubTopicDef[];
  streaming?: boolean;
  /** 仅展示规划阶段（understand 卡）：不显示进度细节，只列子主题名 */
  planOnly?: boolean;
};

function phaseStatusIcon(status: SubtopicProgressNode["search"]["status"]) {
  const s =
    status === "running" ? "running"
    : status === "error" ? "error"
    : status === "done" ? "done"
    : "pending";
  return <StatusIcon status={s} />;
}

/** 子主题规划行（understand 阶段：标题 + 关键词，作为"研究计划"的呈现）。
 *  search 阶段同一份 subTopics 会通过 SubtopicBlock 显示"进度"，两边不再重复——
 *  规划用 query/keywords 体现"想检索什么"，进度用源/命中数体现"实际检索到什么"
 *  （round 3 审查 #H）。 */
function PlanRow({ st, index }: { st: SubTopicDef; index: number }) {
  const title = (st.title ?? "").trim() || `子主题 ${index + 1}`;
  const query = (st.search_query ?? "").trim();
  return (
    <li className="lp-subtopic-plan__item">
      <span className="lp-subtopic-plan__marker">
        <StatusIcon status="pending" />
      </span>
      <div className="lp-subtopic-plan__body">
        <span className="lp-subtopic-plan__title">
          子主题 {index + 1}：{title}
        </span>
        {query ? (
          <span className="lp-subtopic-plan__query">关键词：{query}</span>
        ) : null}
      </div>
    </li>
  );
}

function SourceRow({ source }: { source: SourceNode }) {
  return (
    <li className={`litpilot-search-source litpilot-search-source--${source.status}`}>
      <span className="litpilot-search-source__marker">
        {phaseStatusIcon(source.status)}
      </span>
      <span className="litpilot-search-source__label">
        {source.label}
        {source.failed ? (
          <span className="litpilot-search-source__failure"> 失败</span>
        ) : (
          <span className="litpilot-search-source__hits-inline"> ({source.hits})</span>
        )}
      </span>
    </li>
  );
}

function FilterDetailRow({ item }: { item: FilterDetailItem }) {
  const reason = item.keep ? "" : item.reason ?? "";
  const title = item.title || "(无标题)";
  const variant = item.keep ? "kept" : "rejected";
  const verdict = item.keep
    ? "保留"
    : `剔除 [${item.score ?? "?"}]${reason ? " · " + reason.slice(0, 50) : ""}`;
  return (
    <li className={`litpilot-filter-item litpilot-filter-item--${variant}`}>
      <span className="litpilot-filter-item__dot" aria-hidden="true" />
      <span className="litpilot-filter-item__title" title={title}>{title}</span>
      <span className="litpilot-filter-item__verdict">{verdict}</span>
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
  const pending =
    node.search.status === "running" || node.filter.status === "running";
  const headIconStatus =
    pending ? "running"
    : subtopicDone(node) ? "done"
    : "pending";

  return (
    <div className={`litpilot-search-topic litpilot-search-topic--${pending ? "running" : "done"}`}>
      <button
        type="button"
        className="litpilot-search-topic__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="litpilot-search-topic__marker">
          <StatusIcon status={headIconStatus} />
        </span>
        <span className="litpilot-search-topic__title">{title}</span>
        <span className="litpilot-search-topic__status">{status}</span>
      </button>
      {open ? (
        <ul className="litpilot-search-topic__sources">
          {/* Search phase: per-source details */}
          {node.search.status !== "pending" ? (
            <li key="search" className="litpilot-search-phase">
              <button
                type="button"
                className="litpilot-search-phase__head"
                onClick={() => setSourcesOpen((v) => !v)}
                aria-expanded={sourcesOpen}
              >
                <span className="litpilot-search-phase__marker">
                  {phaseStatusIcon(node.search.status)}
                </span>
                <span className="litpilot-search-phase__label">检索</span>
                <span className="litpilot-search-phase__count">
                  {node.search.detail ?? (node.search.status === "running" ? "进行中…" : "完成")}
                  <span className="litpilot-log-line__chevron" aria-hidden="true">
                    {sourcesOpen ? " ▾" : " ▸"}
                  </span>
                </span>
              </button>
              {sourcesOpen && node.sources.length > 0 ? (
                <ul className="litpilot-search-phase__items">
                  {node.sources.map((src, i) => (
                    <SourceRow key={src.label + "-" + i} source={src} />
                  ))}
                </ul>
              ) : null}
            </li>
          ) : null}

          {/* Filter phase: kept/rejected details */}
          {node.filter.status !== "pending" ? (
            <li key="filter" className="litpilot-search-phase">
              <button
                type="button"
                className="litpilot-search-phase__head"
                onClick={() => setFilterOpen((v) => !v)}
                aria-expanded={filterOpen}
              >
                <span className="litpilot-search-phase__marker">
                  {phaseStatusIcon(node.filter.status)}
                </span>
                <span className="litpilot-search-phase__label">过滤</span>
                <span className="litpilot-search-phase__count">
                  {node.filter.detail ?? (node.filter.status === "running" ? "进行中…" : "完成")}
                  <span className="litpilot-log-line__chevron" aria-hidden="true">
                    {filterOpen ? " ▾" : " ▸"}
                  </span>
                </span>
              </button>
              {filterOpen && node.filterDetails.length > 0 ? (
                <ul className="litpilot-search-phase__items">
                  {node.filterDetails.map((item, i) => (
                    <FilterDetailRow key={item.title + "-" + i} item={item} />
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
  planOnly = false,
}: Props) {
  // planOnly 模式：仅展示规划子主题列表，不构建进度树
  if (planOnly) {
    if (!subTopics?.length) return null;
    return (
      <ul className="lp-subtopic-plan">
        {subTopics.map((st, i) => (
          <PlanRow key={st.id ?? i} st={st} index={i} />
        ))}
      </ul>
    );
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
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
    ? `已完成 ${summary.completedSubtopics}/${summary.totalSubtopics} 个子主题`
    : aggregatePending
      ? `正在检索 · ${summary.completedSubtopics}/${summary.totalSubtopics} 个子主题`
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
