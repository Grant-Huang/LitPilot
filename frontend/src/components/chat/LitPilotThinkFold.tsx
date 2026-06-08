"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { parseThinkSegments } from "@/lib/thinkContent";
import { StatusIcon } from "./StatusIcon";

type Props = {
  content: string;
  /** Phase-level streaming (cursor / label). */
  streaming?: boolean;
  /** Whole-turn streaming; only collapse when this becomes false. */
  turnStreaming?: boolean;
};

export function LitPilotThinkFold({
  content,
  streaming = false,
  turnStreaming,
}: Props) {
  const [open, setOpen] = useState(streaming);
  const contentRef = useRef<HTMLDivElement>(null);
  const wasPhaseStreamingRef = useRef(streaming);
  const wasTurnStreamingRef = useRef(turnStreaming ?? streaming);

  useEffect(() => {
    if (streaming && !wasPhaseStreamingRef.current) {
      setOpen(true);
    }
    const turnActive = turnStreaming ?? streaming;
    if (!turnActive && wasTurnStreamingRef.current) {
      setOpen(false);
    }
    wasPhaseStreamingRef.current = streaming;
    wasTurnStreamingRef.current = turnActive;
  }, [streaming, turnStreaming]);

  const segments = useMemo(() => parseThinkSegments(content), [content]);

  // 标题固定，不再截取模型独白首行
  const headerLabel = streaming ? "模型推理中…" : "模型推理";
  const hasContent = content.trim().length > 0;

  useEffect(() => {
    if (!streaming || !open || !contentRef.current) return;
    contentRef.current.scrollTop = contentRef.current.scrollHeight;
  }, [content, streaming, open]);

  if (!hasContent && !streaming) return null;

  return (
    <div className={`lp-think-fold${open ? " lp-think-fold--open" : ""}${streaming ? " lp-think-fold--streaming" : ""}`}>
      <button
        type="button"
        className="lp-think-fold__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <StatusIcon status={streaming ? "running" : "done"} />
        <span className="lp-think-fold__label">{headerLabel}</span>
        <svg
          className={`lp-think-fold__chevron${open ? " lp-think-fold__chevron--open" : ""}`}
          width="12" height="12" viewBox="0 0 12 12"
          fill="none" stroke="currentColor" strokeWidth="1.5"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden
        >
          <polyline points="2.5,4.5 6,8 9.5,4.5" />
        </svg>
      </button>
      {open ? (
        <div className="lp-think-fold__body">
          <div
            ref={contentRef}
            className="lp-think-fold__content"
            aria-live={streaming ? "polite" : undefined}
          >
            {hasContent
              ? segments.map((seg, idx) =>
                  seg.kind === "system" ? (
                    <p key={idx} className="lp-think-fold__system">{seg.text}</p>
                  ) : (
                    <span key={idx} className="lp-think-fold__model">{seg.text}</span>
                  ),
                )
              : null}
            {streaming ? <span className="lp-think-fold__cursor" aria-hidden="true">▋</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
