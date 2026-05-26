"use client";

import { useState } from "react";
import type { ToolCallState } from "@meso/ui";
import { describeToolAction, previewToolResult } from "@/lib/toolLabels";

type Props = {
  toolCall: ToolCallState;
};

export function LitPilotToolStep({ toolCall }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { call, result, status } = toolCall;
  const title = describeToolAction(call);
  const fullText =
    status === "error"
      ? result?.error || "执行失败"
      : result?.output || "";
  const preview = previewToolResult(result?.output, result?.error);
  const pending = status === "pending" || status === "running";

  return (
    <div
      className={`litpilot-tool-step litpilot-tool-step--${status}`}
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
          <div className="litpilot-tool-step__title">{title}</div>
          {(status === "done" || status === "error") && fullText && (
            <button
              type="button"
              className="litpilot-tool-step__preview"
              onClick={() => setExpanded((o) => !o)}
              aria-expanded={expanded}
              title={expanded ? "收起详情" : "展开详情"}
            >
              {preview}
            </button>
          )}
        </div>
        {result?.duration_ms != null && result.duration_ms > 0 && (
          <span className="litpilot-tool-step__duration">
            {result.duration_ms}ms
          </span>
        )}
      </div>
      {expanded && fullText && (
        <pre className="litpilot-tool-step__detail">{fullText}</pre>
      )}
    </div>
  );
}
