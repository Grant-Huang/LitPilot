"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { dropStaleSysSegments, parseThinkSegments } from "@/lib/thinkContent";
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
  const userToggledRef = useRef(false);

  useEffect(() => {
    if (streaming && !wasPhaseStreamingRef.current) {
      setOpen(true);
    }
    // Phase 结束 → 自动折叠（round 3 审查 #7）。原先只在整轮结束时折叠，但用户希望
    // 二级标题（同"模型推理"层级）在所属 stage 完成时就收起，避免做完一阶段还要
    // 手动收。userToggledRef 保护手动展开的意图。
    if (!streaming && wasPhaseStreamingRef.current && !userToggledRef.current) {
      setOpen(false);
    }
    const turnActive = turnStreaming ?? streaming;
    if (!turnActive && wasTurnStreamingRef.current && !userToggledRef.current) {
      setOpen(false);
    }
    wasPhaseStreamingRef.current = streaming;
    wasTurnStreamingRef.current = turnActive;
  }, [streaming, turnStreaming]);

  const allSegments = useMemo(() => parseThinkSegments(content), [content]);
  const segments = useMemo(() => dropStaleSysSegments(allSegments), [allSegments]);

  // 用第一条 sys 段作为 stage-specific 标题（round 3 审查 #2）。后端通常用 sys 段
  // 携带"正在 X…" 形式的阶段标签，剥离前缀和省略号后即得到稳定的 section 标题。
  // 找不到 sys 段时回落到通用的 "模型推理"。
  const stageLabel = useMemo(() => {
    const firstSys = allSegments.find((s) => s.kind === "system");
    const text = firstSys?.text?.trim();
    if (!text) return null;
    const cleaned = text
      .replace(/^正在/, "")
      .replace(/[…\.]+$/, "")
      .trim();
    if (!cleaned) return null;
    return cleaned.length > 24 ? cleaned.slice(0, 24) : cleaned;
  }, [allSegments]);

  const headerLabel = stageLabel
    ? (streaming ? `${stageLabel}…` : stageLabel)
    : (streaming ? "模型推理中…" : "模型推理");
  const hasContent = content.trim().length > 0;

  useEffect(() => {
    if (!streaming || !open || !contentRef.current) return;
    contentRef.current.scrollTop = contentRef.current.scrollHeight;
  }, [content, streaming, open]);

  if (!hasContent && !streaming) return null;

  const handleToggle = () => {
    userToggledRef.current = true;
    setOpen((o) => !o);
  };

  return (
    <div className={`lp-think-fold${open ? " lp-think-fold--open" : ""}${streaming ? " lp-think-fold--streaming" : ""}`}>
      <button
        type="button"
        className="lp-think-fold__header"
        onClick={handleToggle}
        aria-expanded={open}
      >
        <StatusIcon status={streaming ? "running" : "done"} />
        <span className="lp-think-fold__label">{headerLabel}</span>
        <span className="lp-think-fold__chevron" aria-hidden="true">
          {open ? " ▾" : " ▸"}
        </span>
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
                    <p key={idx} className="lp-think-fold__model">{seg.text}</p>
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
