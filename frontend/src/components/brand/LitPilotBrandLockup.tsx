"use client";

import Link from "next/link";
import { LitPilotMark, LitPilotWordmark } from "@/components/brand/LitPilotMark";

type Props = {
  markSize?: number;
  wordmarkSize?: number;
  /** 例如 chat 页的「文献综述」 */
  pageTitle?: string;
  className?: string;
  /** 点击品牌回到主页；传 false 禁用链接 */
  href?: string | false;
};

/** 侧栏 / 顶栏统一：黑橙 Mark + Wordmark（可选页面副标题） */
export function LitPilotBrandLockup({
  markSize = 26,
  wordmarkSize = 15,
  pageTitle,
  className = "",
  href = "/chat",
}: Props) {
  const brand = (
    <>
      <LitPilotMark size={markSize} aria-hidden={href !== false} />
      <LitPilotWordmark size={wordmarkSize} />
    </>
  );

  return (
    <span className={`litpilot-brand-lockup${className ? ` ${className}` : ""}`}>
      {href !== false ? (
        <Link href={href} className="litpilot-brand-lockup__home" aria-label="回到主页">
          {brand}
        </Link>
      ) : (
        brand
      )}
      {pageTitle ? (
        <span className="litpilot-brand-lockup__page">{pageTitle}</span>
      ) : null}
    </span>
  );
}
