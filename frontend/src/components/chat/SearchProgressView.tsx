"use client";

import { useMemo, useState } from "react";
import {
  buildSearchProgressTree,
  searchAggregate,
  formatSearchDone,
  subtopicDisplayTitle,
  subtopicStatusLabel,
  subtopicDone,
  type SubtopicProgressNode,
  type SourceNode,
  type FilterDetailItem,
} from "@/lib/searchProgressTree";
import { StatusIcon } from "./StatusIcon";
import { KeywordChips } from "./KeywordChips";
import { CountUp } from "./CountUp";

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
        {query ? <KeywordChips query={query} /> : null}
      </div>
    </li>
  );
}

function SourceRow({ source }: { source: SourceNode }) {
  return (
    <li className={`lp-disclosure-row litpilot-search-source--${source.status}`}>
      <span className="lp-disclosure-row__marker">
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
    <li className={`lp-disclosure-row litpilot-filter-item--${variant}`}>
      <span className="lp-disclosure-row__marker">
        <StatusIcon status={item.keep ? "done" : "pending"} />
      </span>
      <span className="litpilot-filter-item__title" title={title}>{title}</span>
      <span className="litpilot-filter-item__verdict">{verdict}</span>
    </li>
  );
}

/** 子主题块（2 层结构）：一行标题/状态，点击展开「查看详情」披露——
 *  把原先 检索/过滤 两层 phase 行收掉，直接平铺检索源与过滤结果两组。 */
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
  const pending =
    node.search.status === "running" || node.filter.status === "running";
  const headIconStatus =
    pending ? "running"
    : subtopicDone(node) ? "done"
    : "pending";
  const hasDetail = node.sources.length > 0 || node.filterDetails.length > 0;

  return (
    <div className={`litpilot-search-topic litpilot-search-topic--${pending ? "running" : "done"}`}>
      <button
        type="button"
        className="litpilot-search-topic__head"
        onClick={hasDetail ? () => setOpen((v) => !v) : undefined}
        aria-expanded={hasDetail ? open : undefined}
        disabled={!hasDetail}
      >
        <span className="litpilot-search-topic__marker">
          <StatusIcon status={headIconStatus} />
        </span>
        <span className="litpilot-search-topic__title">{title}</span>
        <span className="litpilot-search-topic__status">{status}</span>
        {hasDetail ? (
          <span className="litpilot-log-line__chevron" aria-hidden="true">
            {open ? " ▾" : " ▸"}
          </span>
        ) : null}
      </button>
      <div
        className={`litpilot-search-topic__detail-wrap${
          open && hasDetail ? " litpilot-search-topic__detail-wrap--open" : ""
        }`}
      >
        <div className="litpilot-search-topic__detail">
          {node.sources.length > 0 ? (
            <div className="litpilot-search-detail-group">
              <p className="litpilot-search-detail-group__label">
                {phaseStatusIcon(node.search.status)} 检索源
              </p>
              <ul className="lp-disclosure-rows">
                {node.sources.map((src, i) => (
                  <SourceRow key={src.label + "-" + i} source={src} />
                ))}
              </ul>
            </div>
          ) : null}
          {node.filterDetails.length > 0 ? (
            <div className="litpilot-search-detail-group">
              <p className="litpilot-search-detail-group__label">
                {phaseStatusIcon(node.filter.status)} 过滤
                {node.filter.detail ? (
                  <span className="litpilot-search-detail-group__count">
                    {" "}
                    {node.filter.detail}
                  </span>
                ) : null}
              </p>
              <ul className="lp-disclosure-rows">
                {node.filterDetails.map((item, i) => (
                  <FilterDetailRow key={item.title + "-" + i} item={item} />
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
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
  const agg = searchAggregate(summary);
  const showRunning = streaming && !summary.allDone;

  return (
    <div className="litpilot-search-progress" role="list">
      {showRunning ? (
        <p className="litpilot-search-progress__aggregate litpilot-stream-shimmer">
          检索中 · <CountUp value={agg.completed} />/{agg.total} 子主题
          {agg.hits > 0 ? (
            <>
              {" · 命中 "}
              <CountUp value={agg.hits} />
            </>
          ) : null}
        </p>
      ) : agg.total > 0 ? (
        <p className="litpilot-search-progress__aggregate">{formatSearchDone(agg)}</p>
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
