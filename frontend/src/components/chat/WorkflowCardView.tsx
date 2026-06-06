"use client";

import { useMemo, useState } from "react";
import { LitPilotToolStep } from "./LitPilotToolStep";
import { toolStepToState } from "@/lib/executionTrace";
import { summarizeWorkflowCard } from "@/lib/turnCompletion";
import {
  filterVisibleWorkflowSteps,
  formatInlineLogLine,
} from "@/lib/workflowStepFilter";
import type { WorkflowCard, WorkflowStep } from "@/lib/turnWorkflow";
import type { ExecutionTrace } from "@/lib/executionTrace";

type Props = {
  card: WorkflowCard;
  trace?: ExecutionTrace;
  streaming?: boolean;
  defaultOpen?: boolean;
  forceOpen?: boolean;
};

function WorkflowInlineLogLine({ step }: { step: WorkflowStep }) {
  const { primary, outcome } = formatInlineLogLine(step);
  const pending = step.status === "running" || step.status === "pending";
  return (
    <div
      className={`litpilot-log-line litpilot-log-line--${step.status}${
        step.status === "error" ? " litpilot-log-line--error" : ""
      }`}
      role="listitem"
    >
      <span className="litpilot-log-line__marker" aria-hidden="true">
        {pending ? <span className="litpilot-log-line__spinner" /> : "·"}
      </span>
      <p className="litpilot-log-line__text">
        <span className="litpilot-log-line__primary">{primary}</span>
        {outcome ? (
          <span className="litpilot-log-line__outcome"> → {outcome}</span>
        ) : null}
      </p>
    </div>
  );
}

export function WorkflowCardView({
  card,
  trace,
  streaming = false,
  defaultOpen = false,
  forceOpen,
}: Props) {
  const locked = card.locked || card.type === "clarify";
  const isRunning = card.state === "running";
  const [manualOpen, setManualOpen] = useState(false);
  const open = forceOpen || locked || isRunning || defaultOpen || manualOpen;

  const cardSummary = useMemo(() => summarizeWorkflowCard(card), [card]);

  const visibleSteps = useMemo(
    () => filterVisibleWorkflowSteps(card.steps),
    [card.steps],
  );

  const statusLabel =
    card.state === "running"
      ? "进行中"
      : card.state === "error"
        ? "失败"
        : null;

  if (!open && card.state === "done" && !locked) {
    return (
      <button
        type="button"
        className="litpilot-wf-card litpilot-wf-card--collapsed"
        onClick={() => setManualOpen(true)}
        aria-expanded={false}
      >
        <span className="litpilot-wf-card__collapsed-mark" aria-hidden="true">
          ✓
        </span>
        <span className="litpilot-wf-card__collapsed-title">{card.title}</span>
        <span className="litpilot-wf-card__collapsed-summary">{cardSummary}</span>
      </button>
    );
  }

  return (
    <section
      className={`litpilot-wf-card litpilot-wf-card--${card.state}${
        open ? " litpilot-wf-card--open" : ""
      }${streaming && isRunning ? " litpilot-wf-card--live" : ""}`}
    >
      <div className="litpilot-wf-card__head">
        {locked || isRunning ? (
          <span className="litpilot-wf-card__title">{card.title}</span>
        ) : (
          <button
            type="button"
            className="litpilot-wf-card__title-btn"
            onClick={() => setManualOpen((o) => !o)}
            aria-expanded={open}
          >
            {card.title}
          </button>
        )}
        {statusLabel ? (
          <span className="litpilot-wf-card__status">{statusLabel}</span>
        ) : null}
      </div>
      {open ? (
        <div className="litpilot-wf-card__body">
          {card.body ? (
            <div className="litpilot-wf-card__body-text">{card.body}</div>
          ) : null}
          <div className="litpilot-log-lines" role="list">
            {visibleSteps.map((step) => {
              if (step.kind === "tool" && trace) {
                const tool = trace.tools.find(
                  (t, idx) => `tool-${t.id}-${idx}` === step.key,
                );
                if (tool) {
                  return (
                    <LitPilotToolStep
                      key={step.key}
                      toolCall={toolStepToState(tool)}
                    />
                  );
                }
              }
              return <WorkflowInlineLogLine key={step.key} step={step} />;
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}
