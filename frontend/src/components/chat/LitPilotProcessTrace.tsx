"use client";

import { useMemo, useState } from "react";
import { StageTimeline, type Stage } from "@meso.ai/ui";
import type { ExecutionTrace } from "@/lib/executionTrace";
import {
  buildProcessLines,
  traceHasProcessContent,
} from "@/lib/executionTrace";
import { LitPilotThinkFold } from "./LitPilotThinkFold";
import { LitPilotToolStep } from "./LitPilotToolStep";
import { WebFetchStepTitle } from "./WebFetchStepTitle";
import { isWebFetchCharOnlyPreview } from "@/lib/toolLabels";
import { toolStepToState, type WebFetchLineMeta } from "@/lib/executionTrace";

type Props = {
  trace: ExecutionTrace;
  /** 流式思考中 */
  thinkStreaming?: boolean;
  defaultCollapsed?: boolean;
};

function LitPilotWorkflowStep({
  title,
  webFetch,
  status,
  preview,
  detail,
  duration_ms,
}: {
  title: string;
  webFetch?: WebFetchLineMeta;
  status: "pending" | "running" | "done" | "error";
  preview?: string;
  detail?: string;
  duration_ms?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const pending = status === "pending" || status === "running";

  return (
    <div
      className={`litpilot-tool-step litpilot-tool-step--${status === "running" ? "running" : status}`}
      role="listitem"
    >
      <div className="litpilot-tool-step__row">
        <span className="litpilot-tool-step__icon" aria-hidden="true">
          {pending ? (
            <span className="litpilot-tool-step__spinner" />
          ) : status === "error" ? (
            <span className="litpilot-tool-step__icon-mark">×</span>
          ) : (
            <span className="litpilot-tool-step__icon-mark">✓</span>
          )}
        </span>
        <div className="litpilot-tool-step__main">
          <div className="litpilot-tool-step__title">
            {webFetch ? (
              <WebFetchStepTitle
                articleTitle={webFetch.articleTitle}
                url={webFetch.url}
                prefix={webFetch.prefix ?? "抓取网页："}
                charCount={webFetch.charCount}
              />
            ) : (
              title
            )}
          </div>
          {preview &&
            (status === "done" || status === "error") &&
            !(webFetch && isWebFetchCharOnlyPreview(preview, undefined)) && (
            <button
              type="button"
              className="litpilot-tool-step__preview"
              onClick={() => detail && setExpanded((o) => !o)}
              aria-expanded={expanded}
              disabled={!detail}
            >
              {preview}
            </button>
          )}
        </div>
        {duration_ms != null && duration_ms > 0 && (
          <span className="litpilot-tool-step__duration">{duration_ms}ms</span>
        )}
      </div>
      {expanded && detail && (
        <pre className="litpilot-tool-step__detail">{detail}</pre>
      )}
    </div>
  );
}

export function LitPilotProcessTrace({
  trace,
  thinkStreaming = false,
  defaultCollapsed = false,
}: Props) {
  const [open, setOpen] = useState(!defaultCollapsed);
  const lines = useMemo(() => buildProcessLines(trace), [trace]);
  const doneCount = lines.filter((l) => l.status === "done").length;
  const errCount = lines.filter((l) => l.status === "error").length;

  if (!traceHasProcessContent(trace)) return null;

  const stages: Stage[] = trace.stages.map((s) => ({
    id: s.name,
    label: s.name,
    status:
      s.state === "done" || s.state === "error" ? "done" : "active",
  }));

  let summary = "执行过程";
  if (lines.length) {
    const parts: string[] = [];
    if (doneCount) parts.push(`${doneCount} 步完成`);
    if (errCount) parts.push(`${errCount} 步失败`);
    summary = parts.length ? parts.join(" · ") : `共 ${lines.length} 步`;
  }

  return (
    <div
      className={`litpilot-process${open ? " litpilot-process--open" : ""}`}
    >
      <button
        type="button"
        className="litpilot-process__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="litpilot-process__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span>{summary}</span>
      </button>
      {open && (
        <div className="litpilot-process__body">
          {trace.thinkContent ? (
            <LitPilotThinkFold
              content={trace.thinkContent}
              collapsed={false}
              streaming={thinkStreaming}
            />
          ) : null}
          {stages.length > 0 && (
            <div className="litpilot-process__stages">
              <StageTimeline stages={stages} />
            </div>
          )}
          {lines.length > 0 && (
            <div
              className="litpilot-tool-steps litpilot-process__steps"
              role="list"
              aria-label="执行步骤"
            >
              {lines.map((line) => {
                const tool = trace.tools.find(
                  (t, idx) => `tool-${t.id}-${idx}` === line.key,
                );
                if (tool) {
                  return (
                    <LitPilotToolStep
                      key={line.key}
                      toolCall={toolStepToState(tool)}
                    />
                  );
                }
                return (
                  <LitPilotWorkflowStep
                    key={line.key}
                    title={line.title}
                    webFetch={line.webFetch}
                    status={line.status}
                    preview={line.preview}
                    detail={line.detail}
                    duration_ms={line.duration_ms}
                  />
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
