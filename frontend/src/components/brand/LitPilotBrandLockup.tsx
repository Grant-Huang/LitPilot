"use client";

import { LitPilotMark, LitPilotWordmark } from "@/components/brand/LitPilotMark";

type Props = {
  markSize?: number;
  wordmarkSize?: number;
  /** 例如 chat 页的「文献综述」 */
  pageTitle?: string;
  className?: string;
};

/** 侧栏 / 顶栏统一：黑橙 Mark + Wordmark（可选页面副标题） */
export function LitPilotBrandLockup({
  markSize = 26,
  wordmarkSize = 15,
  pageTitle,
  className = "",
}: Props) {
  return (
    <span className={`litpilot-brand-lockup${className ? ` ${className}` : ""}`}>
      <LitPilotMark size={markSize} aria-label="LitPilot" />
      <LitPilotWordmark size={wordmarkSize} />
      {pageTitle ? (
        <span className="litpilot-brand-lockup__page">{pageTitle}</span>
      ) : null}
    </span>
  );
}
