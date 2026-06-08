"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { parseThinkSegments } from "@/lib/thinkContent";

type Props = {
  content: string;
  streaming?: boolean;
};

/** 与流式输出同款的思考折叠块；系统注记（⟦sys⟧）灰色显示。 */
export function LitPilotThinkFold({ content, streaming = false }: Props) {
  const [open, setOpen] = useState(streaming);
  const contentRef = useRef<HTMLDivElement>(null);
  const wasStreamingRef = useRef(streaming);

  useEffect(() => {
    if (streaming && !wasStreamingRef.current) {
      setOpen(true);
    }
    if (!streaming && wasStreamingRef.current) {
      setOpen(false);
    }
    wasStreamingRef.current = streaming;
  }, [streaming]);

  const segments = useMemo(() => parseThinkSegments(content), [content]);

  const hasContent = content.trim().length > 0;

  useEffect(() => {
    if (!streaming || !open || !contentRef.current) return;
    contentRef.current.scrollTop = contentRef.current.scrollHeight;
  }, [content, streaming, open]);

  if (!hasContent && !streaming) return null;

  const label = streaming ? "思考中" : "推理过程";

  return (
    <div
      className={`meso-think litpilot-think${
        open ? " meso-think--open" : ""
      }${streaming ? " litpilot-think--streaming" : ""}`}
    >
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
        <span className="meso-think__label">{label}</span>
        {streaming && open ? (
          <span className="meso-think__dot litpilot-think__dot" aria-label="思考中" />
        ) : null}
      </button>
      {open ? (
        <div className="meso-think__body litpilot-think__body">
          <div
            ref={contentRef}
            className="meso-think__content litpilot-think__content"
            aria-live={streaming ? "polite" : undefined}
          >
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
            {streaming ? (
              <span className="meso-think__cursor" aria-hidden="true">
                ▋
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
