"use client";

import { useEffect, useMemo, useState } from "react";
import { SearchProgressView } from "./SearchProgressView";
import { LitPilotToolStep } from "./LitPilotToolStep";
import { LitPilotThinkFold } from "./LitPilotThinkFold";
import { StatusIcon } from "./StatusIcon";
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
  forceOpen?: boolean;
  extensions?: Array<{ name: string; data: Record<string, unknown> }>;
};

function WorkflowInlineLogLine({ step }: { step: WorkflowStep }) {
  const [expanded, setExpanded] = useState(false);
  const { primary, outcome } = formatInlineLogLine(step);
  const hasDetail = Boolean(step.detail);
  const iconStatus =
    step.status === "running" || step.status === "pending"
      ? "running"
      : step.status === "error"
        ? "error"
        : "done";

  const rowContent = (
    <>
      <span className="litpilot-log-line__primary">{primary}</span>
      {outcome ? (
        <span className="litpilot-log-line__outcome"> {outcome}</span>
      ) : null}
      {hasDetail ? (
        <span className="litpilot-log-line__chevron" aria-hidden="true">
          {expanded ? " ▾" : " ▸"}
        </span>
      ) : null}
    </>
  );

  return (
    <div
      className={`litpilot-log-line litpilot-log-line--${step.status}${
        step.status === "error" ? " litpilot-log-line--error" : ""
      }`}
      role="listitem"
    >
      <span className="litpilot-log-line__marker">
        <StatusIcon status={iconStatus} />
      </span>
      <div className="litpilot-log-line__body">
        {hasDetail ? (
          <button
            type="button"
            className="litpilot-log-line__text litpilot-log-line__text--toggle"
            onClick={() => setExpanded((o) => !o)}
            aria-expanded={expanded}
          >
            {rowContent}
          </button>
        ) : (
          <p className="litpilot-log-line__text">{rowContent}</p>
        )}
        {expanded && step.detail ? (
          <pre className="litpilot-log-line__detail">{step.detail}</pre>
        ) : null}
      </div>
    </div>
  );
}

function cardHeadStatus(
  card: WorkflowCard,
  isRunning: boolean,
  hasThinkStream: boolean,
): "running" | "done" | "pending" {
  if (isRunning && !hasThinkStream) return "running";
  if (card.state === "done") return "done";
  return "pending";
}

function renderStepLogLines(
  steps: WorkflowStep[],
  trace?: ExecutionTrace,
  visibleSteps?: WorkflowStep[],
) {
  const target = visibleSteps ?? steps;
  const filtered = filterVisibleWorkflowSteps(target);
  if (!filtered.length) return null;
  return (
    <div className="litpilot-log-lines" role="list">
      {filtered.map((step) => {
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
  );
}

function formatToolOneLiner(step: WorkflowStep): string | null {
  if (step.kind !== "tool") return null;
  if (step.status === "pending") return null;
  const primary = step.title;
  const duration = step.duration_ms
    ? ` · ${(step.duration_ms / 1000).toFixed(1)}s`
    : "";
  const preview = step.preview ? ` · ${step.preview}` : "";
  const tag = step.status === "running" ? "⚙ " : step.status === "error" ? "⚠ " : "✓ ";
  const text = `${tag}${primary}${preview}${duration}`;
  return text.length > 120 ? text.slice(0, 117) + "…" : text;
}

export function WorkflowCardView({
  card,
  trace,
  streaming = false,
  forceOpen,
  extensions = [],
}: Props) {
  const locked = card.locked || card.type === "clarify";
  const isRunning = card.state === "running";

  const [userIntent, setUserIntent] = useState<boolean | null>(null);

  useEffect(() => {
    if (!streaming) setUserIntent(null);
  }, [streaming]);

  // 卡片默认折叠：只有 forceOpen / locked / 用户手动展开 时才打开
  const systemOpen = forceOpen || locked;

  const open = userIntent !== null ? userIntent : systemOpen;

  const canToggle = !locked;

  const pinnedThink = card.pinnedThink?.trim() ?? "";

  const cardSummary = useMemo(
    () => summarizeWorkflowCard(card, { trace, extensions }),
    [card, trace, extensions],
  );

  const visibleSteps = useMemo(
    () => filterVisibleWorkflowSteps(card.steps),
    [card.steps],
  );

  const toolSteps = useMemo(
    () => visibleSteps.filter((s) => s.kind === "tool"),
    [visibleSteps],
  );

  const headSummary = useMemo(() => {
    if (card.state === "done" && cardSummary) return { text: cardSummary, className: "litpilot-wf-card__inline-summary" };
    if (toolSteps.length === 0) return null;
    const latest = toolSteps[toolSteps.length - 1];
    const text = formatToolOneLiner(latest);
    if (!text) return null;
    return { text, className: "litpilot-wf-card__carousel-summary" };
  }, [card.state, cardSummary, toolSteps]);

  const liveThink = trace?.thinkContent?.trim() ?? "";
  const thinkForCard = card.type === "search"
    ? pinnedThink
    : isRunning ? liveThink : pinnedThink;
  const hasThinkStream = card.type === "search"
    ? Boolean(pinnedThink)
    : (card.type === "understand" || card.type === "brief") &&
      Boolean(thinkForCard || (streaming && isRunning));

  const headStatus = cardHeadStatus(card, isRunning, hasThinkStream);

  return (
    <section
      className={`litpilot-wf-card litpilot-wf-card--${card.state}${
        open ? " litpilot-wf-card--open" : ""
      }${streaming && isRunning ? " litpilot-wf-card--live" : ""}`}
    >
      <div
        className="litpilot-wf-card__head"
        onClick={canToggle ? () => setUserIntent((prev) => (prev !== null ? !prev : !systemOpen)) : undefined}
        style={canToggle ? { cursor: "pointer" } : undefined}
        role={canToggle ? "button" : undefined}
        tabIndex={canToggle ? 0 : undefined}
        aria-expanded={open}
      >
        <span className="litpilot-wf-card__marker">
          <StatusIcon status={headStatus} />
        </span>
        <span className="litpilot-wf-card__title">{card.title}</span>
        {!open && headSummary ? (
          <span className={headSummary.className}>
            {headSummary.text}
          </span>
        ) : null}
        <span className="litpilot-wf-card__chevron" aria-hidden="true">
          {open ? " ▾" : " ▸"}
        </span>
      </div>
      {open ? (
        <div className="litpilot-wf-card__body">
          {hasThinkStream ? (
            <LitPilotThinkFold
              content={thinkForCard}
              streaming={streaming && isRunning}
              turnStreaming={streaming}
            />
          ) : null}
          {card.body && card.type !== "understand" && card.type !== "search" ? (
            <div className="litpilot-wf-card__body-text">{card.body}</div>
          ) : null}
          {card.type === "understand" && card.subTopics?.length ? (
            <SearchProgressView
              extensions={[]}
              subTopics={card.subTopics}
              planOnly
            />
          ) : null}
          {card.type === "search" ? (
            <SearchProgressView
              extensions={
                extensions.length > 0
                  ? extensions
                  : (card.progressExtensions ?? [])
              }
              subTopics={card.subTopics}
              streaming={streaming && isRunning}
            />
          ) : null}
          {renderStepLogLines(card.steps, trace, visibleSteps)}
        </div>
      ) : null}
    </section>
  );
}
