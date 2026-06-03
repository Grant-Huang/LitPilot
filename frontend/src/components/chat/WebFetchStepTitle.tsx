"use client";

import { WEB_FETCH_PREFIX, webFetchDisplayTitle } from "@/lib/toolLabels";

type Props = {
  articleTitle: string;
  url: string;
  prefix?: string;
  /** 抓取正文字数，展示在 [url] 之后 */
  charCount?: number;
};

/** 抓取步骤标题：文章标题 + 可点击 [url] 链接（不展示裸 URL 字符串） */
export function WebFetchStepTitle({
  articleTitle,
  url,
  prefix = WEB_FETCH_PREFIX,
  charCount,
}: Props) {
  const title = webFetchDisplayTitle(articleTitle);
  const href = url.trim();

  return (
    <span className="litpilot-tool-step__title">
      {prefix}
      {title}
      {href ? (
        <>
          {" ["}
          <a
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="litpilot-tool-step__link"
            title={href}
            onClick={(e) => e.stopPropagation()}
          >
            url
          </a>
          {"]"}
        </>
      ) : null}
      {charCount != null && charCount > 0 ? (
        <span className="litpilot-tool-step__char-count">
          （约 {charCount} 字）
        </span>
      ) : null}
    </span>
  );
}
