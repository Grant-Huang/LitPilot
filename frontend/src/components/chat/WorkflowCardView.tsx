"use client";

import { useEffect, useMemo, useState } from "react";
import { SearchProgressView } from "./SearchProgressView";
import { SubtopicListView } from "./SubtopicListView";
import { LitPilotToolStep } from "./LitPilotToolStep";
import { LitPilotThinkFold } from "./LitPilotThinkFold";
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
  extensions?: Array<{ name: string; data: Record<string, unknown> }>;
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

function cardHeadMarker(
  card: WorkflowCard,
  open: boolean,
  isRunning: boolean,
): string | "spinner" {
  if (isRunning) return "spinner";
  if (card.state === "done") return open ? "▾" : "✓";
  return open ? "▾" : "▸";
}

export function WorkflowCardView({
  card,
  trace,
  streaming = false,
  defaultOpen = false,
  forceOpen,
  extensions = [],
}: Props) {
  const locked = card.locked || card.type === "clarify";
  const isRunning = card.state === "running";
  const [manualOpen, setManualOpen] = useState(false);

  useEffect(() => {
    if (!streaming) setManualOpen(false);
  }, [streaming]);

  const open =
    forceOpen ||
    locked ||
    isRunning ||
    (streaming && defaultOpen) ||
    manualOpen;
  const canToggle = !locked && !isRunning && card.state === "done";

  const cardSummary = useMemo(
    () => summarizeWorkflowCard(card, { trace, extensions }),
    [card, trace, extensions],
  );

  const visibleSteps = useMemo(
    () => filterVisibleWorkflowSteps(card.steps),
    [card.steps],
  );

  const statusLabel = isRunning && open ? "进行中" : null;

  const marker = cardHeadMarker(card, open, isRunning);

  return (
    <section
      className={`litpilot-wf-card litpilot-wf-card--${card.state}${
        open ? " litpilot-wf-card--open" : ""
      }${streaming && isRunning ? " litpilot-wf-card--live" : ""}`}
    >
      <div className="litpilot-wf-card__head">
        <span className="litpilot-wf-card__marker" aria-hidden="true">
          {marker === "spinner" ? (
            <span className="litpilot-log-line__spinner" />
          ) : (
            marker
          )}
        </span>
        {canToggle ? (
          <button
            type="button"
            className="litpilot-wf-card__title-btn"
            onClick={() => setManualOpen((o) => !o)}
            aria-expanded={open}
          >
            {card.title}
          </button>
        ) : (
          <span className="litpilot-wf-card__title">{card.title}</span>
        )}
        {!open && cardSummary ? (
          <span className="litpilot-wf-card__inline-summary">{cardSummary}</span>
        ) : null}
        {open && statusLabel ? (
          <span className="litpilot-wf-card__status">{statusLabel}</span>
        ) : null}
      </div>
      {open ? (
        <div className="litpilot-wf-card__body">
          {trace?.thinkContent &&
          (card.type === "understand" || card.type === "brief") ? (
            <LitPilotThinkFold
              content={trace.thinkContent}
              collapsed={!(streaming && isRunning)}
              streaming={streaming && isRunning}
            />
          ) : null}
          {card.body ? (
            <div className="litpilot-wf-card__body-text">{card.body}</div>
          ) : null}
          {card.type === "understand" && card.subTopics?.length ? (
            <SubtopicListView subTopics={card.subTopics} />
          ) : null}
          {card.type === "search" ? (
            <SearchProgressView
              extensions={extensions}
              subTopics={card.subTopics}
              streaming={streaming && isRunning}
            />
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
