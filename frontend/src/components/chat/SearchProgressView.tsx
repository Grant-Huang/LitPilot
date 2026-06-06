"use client";

import { useMemo, useState } from "react";
import {
  buildSearchProgressTree,
  sourceStatusLabel,
  topicDisplayTitle,
  topicStatusLabel,
  type SearchTopicNode,
} from "@/lib/searchProgressTree";

type Props = {
  extensions: Array<{ name: string; data: Record<string, unknown> }>;
  subTopics?: Array<{ id?: string; title?: string; search_query?: string }>;
  streaming?: boolean;
};

function TopicBlock({
  topic,
  defaultOpen,
}: {
  topic: SearchTopicNode;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const title = topicDisplayTitle(topic);
  const status = topicStatusLabel(topic);
  const pending = topic.status === "running";

  return (
    <div
      className={`litpilot-search-topic litpilot-search-topic--${topic.status}`}
    >
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
          {topic.sources.map((src) => {
            const running = src.status === "running";
            const failed = src.status === "error" || src.failed;
            const previews = src.topHits.length
              ? src.topHits
              : src.topUrls.map((url) => ({ url, title: url }));
            return (
              <li
                key={src.source}
                className={`litpilot-search-source litpilot-search-source--${src.status}${
                  failed ? " litpilot-search-source--failed" : ""
                }`}
              >
                <span className="litpilot-search-source__marker" aria-hidden="true">
                  {running ? (
                    <span className="litpilot-log-line__spinner" />
                  ) : failed ? (
                    "×"
                  ) : (
                    "·"
                  )}
                </span>
                <div className="litpilot-search-source__body">
                  <span
                    className={`litpilot-search-source__label${
                      failed ? " litpilot-search-source__label--failed" : ""
                    }`}
                  >
                    {src.label}
                  </span>
                  <span className="litpilot-search-source__status">
                    {sourceStatusLabel(src)}
                  </span>
                  {running && src.query ? (
                    <span className="litpilot-search-source__query" title={src.query}>
                      {src.query.slice(0, 96)}
                    </span>
                  ) : null}
                  {failed && src.query ? (
                    <span
                      className="litpilot-search-source__query litpilot-search-source__query--failed"
                      title={src.query}
                    >
                      {src.query.slice(0, 96)}
                    </span>
                  ) : null}
                  {previews.length > 0 && !failed ? (
                    <ul className="litpilot-search-source__hits">
                      {previews.slice(0, 4).map((hit) => (
                        <li key={hit.url} className="litpilot-search-source__hit">
                          <a
                            href={hit.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={hit.url}
                          >
                            <span className="litpilot-search-source__hit-title">
                              {hit.title.length > 120
                                ? `${hit.title.slice(0, 120)}…`
                                : hit.title}
                            </span>
                            <span className="litpilot-search-source__hit-url">
                              {hit.url.length > 72 ? `${hit.url.slice(0, 72)}…` : hit.url}
                            </span>
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </li>
            );
          })}
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
    () => buildSearchProgressTree(extensions, subTopics),
    [extensions, subTopics],
  );

  if (!summary.topics.length) return null;

  const runningIdx = summary.topics.findIndex((t) => t.status === "running");
  const aggregatePending =
    streaming && !summary.allDone && summary.completedTopics < summary.totalTopics;
  const aggregateLabel = summary.allDone
    ? `检索完成 · ${summary.completedTopics}/${summary.totalTopics} 主题`
    : aggregatePending
      ? `检索中 · ${summary.completedTopics}/${summary.totalTopics} 主题`
      : null;

  return (
    <div className="litpilot-search-progress" role="list">
      {aggregateLabel ? (
        <p className="litpilot-search-progress__aggregate">{aggregateLabel}</p>
      ) : null}
      {summary.topics.map((topic, i) => (
        <TopicBlock
          key={topic.passIndex}
          topic={topic}
          defaultOpen={
            topic.status === "running" ||
            (runningIdx < 0 && i === summary.topics.length - 1 && streaming)
          }
        />
      ))}
    </div>
  );
}
