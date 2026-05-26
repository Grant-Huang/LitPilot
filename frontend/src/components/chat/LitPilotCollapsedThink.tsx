"use client";

import { useState } from "react";

type Props = {
  content: string;
  defaultCollapsed?: boolean;
};

export function LitPilotCollapsedThink({
  content,
  defaultCollapsed = true,
}: Props) {
  const [open, setOpen] = useState(!defaultCollapsed);
  if (!content.trim()) return null;

  return (
    <div className={`litpilot-think${open ? " litpilot-think--open" : ""}`}>
      <button
        type="button"
        className="litpilot-think__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="litpilot-think__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span>思考过程</span>
      </button>
      {open && <div className="litpilot-think__body">{content}</div>}
    </div>
  );
}
