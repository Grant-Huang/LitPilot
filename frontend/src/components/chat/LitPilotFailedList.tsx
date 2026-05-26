"use client";

import { useState } from "react";
import type { FailedLiteratureItem } from "@/lib/collectFailures";

type Props = {
  items: FailedLiteratureItem[];
  defaultCollapsed?: boolean;
};

export function LitPilotFailedList({
  items,
  defaultCollapsed = false,
}: Props) {
  const [open, setOpen] = useState(!defaultCollapsed);
  if (!items.length) return null;

  return (
    <div className={`litpilot-failed${open ? " litpilot-failed--open" : ""}`}>
      <button
        type="button"
        className="litpilot-failed__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="litpilot-failed__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span>未能收录的文献（{items.length}）</span>
      </button>
      {open && (
        <ul className="litpilot-failed__list">
          {items.map((item, i) => (
            <li key={`${item.url}-${i}`} className="litpilot-failed__item">
              <div className="litpilot-failed__kind">{item.kind}</div>
              {item.url.startsWith("http") ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="litpilot-failed__url"
                >
                  {item.title || item.url}
                </a>
              ) : (
                <span className="litpilot-failed__url">{item.url}</span>
              )}
              <div className="litpilot-failed__reason">{item.reason}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
