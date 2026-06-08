"use client";

import { useState } from "react";
import type { ToolCallState } from "@meso.ai/ui";
import { formatToolLogLine } from "@/lib/toolLabels";
import { StatusIcon } from "./StatusIcon";

type Props = {
  toolCall: ToolCallState;
};

export function LitPilotToolStep({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { call, result, status } = toolCall;
  const line = formatToolLogLine(call, result, status);
  const hasDetail = Boolean(line.rawDetail);

  const rowContent = (
    <>
      <span className="litpilot-log-line__primary">{line.primary}</span>
      {line.outcome ? (
        <span className="litpilot-log-line__outcome"> {line.outcome}</span>
      ) : null}
      {hasDetail ? (
        <span className="litpilot-log-line__chevron" aria-hidden="true">
          {expanded ? " ▾" : " ▸"}
        </span>
      ) : null}
    </>
  );

  return (
    <div
      className={`litpilot-log-line litpilot-log-line--${status}${
        line.error ? " litpilot-log-line--error" : ""
      }`}
      role="listitem"
    >
      <span className="litpilot-log-line__marker">
        <StatusIcon status={line.pending ? "running" : line.error ? "error" : "done"} />
      </span>
      <div className="litpilot-log-line__body">
        {hasDetail ? (
          <button
            type="button"
            className="litpilot-log-line__text litpilot-log-line__text--toggle"
            onClick={() => setExpanded((o) => !o)}
            aria-expanded={expanded}
          >
            {rowContent}
          </button>
        ) : (
          <p className="litpilot-log-line__text">{rowContent}</p>
        )}
        {expanded && line.rawDetail ? (
          <pre className="litpilot-log-line__detail">{line.rawDetail}</pre>
        ) : null}
      </div>
    </div>
  );
}
