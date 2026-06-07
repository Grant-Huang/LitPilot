"use client";

import { useEffect, useMemo, useState } from "react";
import { parseThinkSegments } from "@/lib/thinkContent";

type Props = {
  content: string;
  collapsed?: boolean;
  streaming?: boolean;
};

/** 与流式输出同款的思考折叠块；系统注记（⟦sys⟧）灰色显示。 */
export function LitPilotThinkFold({
  content,
  collapsed = false,
  streaming = false,
}: Props) {
  const [open, setOpen] = useState(!collapsed);

  useEffect(() => {
    if (collapsed) setOpen(false);
  }, [collapsed]);

  const segments = useMemo(() => parseThinkSegments(content), [content]);

  const hasContent = content.trim().length > 0;

  // While streaming, always show the fold header (loading indicator) even before content arrives.
  if (!hasContent && !streaming) return null;

  return (
    <div className={`meso-think litpilot-think${open ? " meso-think--open" : ""}`}>
      <button
        type="button"
        className="meso-think__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <svg
          className="meso-think__chevron"
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <polyline points="3,5 7,9 11,5" />
        </svg>
        <span className="meso-think__label">推理过程</span>
        {streaming && <span className="meso-think__dot" aria-label="推理中" />}
      </button>
      <div className="meso-think__body">
        <div className="meso-think__content litpilot-think__content">
          {hasContent ? (
            segments.map((seg, idx) =>
              seg.kind === "system" ? (
                <p key={idx} className="litpilot-think__system">
                  {seg.text}
                </p>
              ) : (
                <span key={idx} className="litpilot-think__model">
                  {seg.text}
                </span>
              ),
            )
          ) : (
            <p className="litpilot-think__system">正在调用模型…</p>
          )}
          {streaming && (
            <span className="meso-think__cursor" aria-hidden="true">
              ▋
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
