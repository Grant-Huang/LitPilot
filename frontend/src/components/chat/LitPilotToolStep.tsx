"use client";

import { useState } from "react";
import type { ToolCallState } from "@meso.ai/ui";
import { formatToolLogLine } from "@/lib/toolLabels";

type Props = {
  toolCall: ToolCallState;
};

export function LitPilotToolStep({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { call, result, status } = toolCall;
  const line = formatToolLogLine(call, result, status);

  return (
    <div
      className={`litpilot-log-line litpilot-log-line--${status}${
        line.error ? " litpilot-log-line--error" : ""
      }`}
      role="listitem"
    >
      <span className="litpilot-log-line__marker" aria-hidden="true">
        {line.pending ? (
          <span className="litpilot-log-line__spinner" />
        ) : line.error ? (
          "×"
        ) : (
          "·"
        )}
      </span>
      <div className="litpilot-log-line__body">
        <p className="litpilot-log-line__text">
          <span className="litpilot-log-line__primary">{line.primary}</span>
          {line.outcome ? (
            <span className="litpilot-log-line__outcome"> → {line.outcome}</span>
          ) : null}
        </p>
        {line.rawDetail ? (
          <button
            type="button"
            className="litpilot-log-line__detail-toggle"
            onClick={() => setExpanded((o) => !o)}
            aria-expanded={expanded}
          >
            {expanded ? "收起原始响应" : "原始响应"}
          </button>
        ) : null}
        {expanded && line.rawDetail ? (
          <pre className="litpilot-log-line__detail">{line.rawDetail}</pre>
        ) : null}
      </div>
    </div>
  );
}
