"use client";

import { useState } from "react";
import { LitPilotToolStep } from "./LitPilotToolStep";
import { WebFetchStepTitle } from "./WebFetchStepTitle";
import { isWebFetchCharOnlyPreview, WEB_FETCH_PREFIX } from "@/lib/toolLabels";
import { toolStepToState } from "@/lib/executionTrace";
import type { WorkflowCard, WorkflowStep } from "@/lib/turnWorkflow";
import type { ExecutionTrace } from "@/lib/executionTrace";

type Props = {
  card: WorkflowCard;
  trace?: ExecutionTrace;
  defaultOpen?: boolean;
  forceOpen?: boolean;
};

function WorkflowInlineStep({ step }: { step: WorkflowStep }) {
  return (
    <div className={`litpilot-wf-step litpilot-wf-step--${step.status}`}>
      <span className="litpilot-wf-step__dot" aria-hidden="true" />
      <span className="litpilot-wf-step__title">{step.title}</span>
    </div>
  );
}

export function WorkflowCardView({ card, trace, defaultOpen = false, forceOpen }: Props) {
  const locked = card.locked || card.type === "clarify";
  const [open, setOpen] = useState(defaultOpen || forceOpen || locked);

  const doneLabel =
    card.state === "running"
      ? "进行中"
      : card.state === "error"
        ? "失败"
        : "Done";

  return (
    <div
      className={`litpilot-wf-card litpilot-wf-card--${card.state}${
        open ? " litpilot-wf-card--open" : ""
      }`}
    >
      <button
        type="button"
        className="litpilot-wf-card__header"
        onClick={() => {
          if (!locked) setOpen((o) => !o);
        }}
        aria-expanded={open}
        disabled={locked}
      >
        <span className="litpilot-wf-card__chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="litpilot-wf-card__title">{card.title}</span>
        <span className="litpilot-wf-card__status">{doneLabel}</span>
      </button>
      {open && (
        <div className="litpilot-wf-card__body">
          {card.body ? (
            <div className="litpilot-wf-card__body-text">{card.body}</div>
          ) : null}
          {card.steps.map((step) => {
            if (step.kind === "tool" && trace) {
              const tool = trace.tools.find((t, idx) => `tool-${t.id}-${idx}` === step.key);
              if (tool) {
                return <LitPilotToolStep key={step.key} toolCall={toolStepToState(tool)} />;
              }
            }
            if (step.title.includes("抓取") && step.preview) {
              return (
                <div key={step.key} className="litpilot-tool-step litpilot-tool-step--done">
                  <WebFetchStepTitle
                    articleTitle={step.title}
                    url=""
                    prefix={WEB_FETCH_PREFIX}
                  />
                </div>
              );
            }
            return <WorkflowInlineStep key={step.key} step={step} />;
          })}
        </div>
      )}
    </div>
  );
}
