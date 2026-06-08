"use client";

/**
 * 统一状态图标。替换原来遍布各组件的 ▸▾·× spinner 字符，
 * 让全页状态信号来自同一套图标语言。
 */

type Status = "running" | "done" | "error" | "pending" | "warning";

type Props = {
  status: Status;
  className?: string;
};

export function StatusIcon({ status, className = "" }: Props) {
  const base = `lp-status-icon lp-status-icon--${status} ${className}`.trim();

  if (status === "running") {
    return <span className={base} aria-label="进行中"><span className="lp-status-icon__spinner" /></span>;
  }
  if (status === "done") {
    return (
      <span className={base} aria-label="完成">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <polyline points="2,6.5 5,9.5 10,3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className={base} aria-label="失败">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <line x1="3" y1="3" x2="9" y2="9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          <line x1="9" y1="3" x2="3" y2="9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  // pending / warning: 空心圆
  return (
    <span className={base} aria-label={status === "warning" ? "警告" : "等待"}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
        <circle cx="6" cy="6" r="4" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </span>
  );
}
