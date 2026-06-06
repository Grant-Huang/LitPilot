"use client";

import { useMemo, useState } from "react";
import type { TurnWorkflow } from "@/lib/turnWorkflow";
import type { ExecutionTrace } from "@/lib/executionTrace";
import { WorkflowCardView } from "./WorkflowCardView";

type Props = {
  workflow: TurnWorkflow;
  trace?: ExecutionTrace;
  streaming?: boolean;
  defaultCollapsed?: boolean;
};

export function TurnWorkflowBlock({
  workflow,
  trace,
  streaming = false,
  defaultCollapsed = false,
}: Props) {
  const [open, setOpen] = useState(!defaultCollapsed && !workflow.clarifying);
  const runningId = useMemo(() => {
    const running = workflow.cards.find((c) => c.state === "running");
    return running?.id ?? null;
  }, [workflow.cards]);

  if (!workflow.cards.length) return null;

  return (
    <div className={`litpilot-turn-wf${open ? " litpilot-turn-wf--open" : ""}`}>
      <button
        type="button"
        className="litpilot-turn-wf__header"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        disabled={workflow.clarifying}
      >
        <span className="litpilot-turn-wf__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="litpilot-turn-wf__summary">
          {workflow.summary}
          {streaming ? " · 进行中" : ""}
        </span>
      </button>
      {(open || workflow.clarifying) && (
        <div className="litpilot-turn-wf__cards">
          {workflow.cards.map((card) => (
            <WorkflowCardView
              key={card.id}
              card={card}
              trace={trace}
              defaultOpen={card.id === runningId}
              forceOpen={card.type === "clarify"}
            />
          ))}
        </div>
      )}
    </div>
  );
}
