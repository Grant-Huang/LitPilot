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
  defaultOpen?: boolean;
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

function FetchSubsectionBlock({
  label,
  steps,
  trace,
}: {
  label: string;
  steps: WorkflowStep[];
  trace?: ExecutionTrace;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="litpilot-wf-subsection">
      <button
        type="button"
        className="litpilot-wf-subsection__head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="litpilot-wf-subsection__marker" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="litpilot-wf-subsection__label">{label}</span>
      </button>
      {open ? renderStepLogLines(steps, trace) : null}
    </div>
  );
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

  // null = 用户未操作（跟随系统默认）；true/false = 用户操作，锁定意图
  const [userIntent, setUserIntent] = useState<boolean | null>(null);

  // 流结束后清除用户意图，让下一轮 turn 回到系统默认
  useEffect(() => {
    if (!streaming) setUserIntent(null);
  }, [streaming]);

  const pinnedThink = card.pinnedThink?.trim() ?? "";
  const hasBriefBody = Boolean(card.body?.trim());
  const retainWhileStreaming =
    streaming &&
    card.state === "done" &&
    (card.type === "understand" || card.type === "brief") &&
    (Boolean(pinnedThink) || hasBriefBody);

  // 系统默认开/关
  const systemOpen =
    forceOpen ||
    locked ||
    isRunning ||
    (streaming && defaultOpen) ||
    retainWhileStreaming;

  // 用户意图优先；未操作时走系统默认
  const open = userIntent !== null ? userIntent : systemOpen;
  const canToggle = !locked && !isRunning && card.state === "done";

  const cardSummary = useMemo(
    () => summarizeWorkflowCard(card, { trace, extensions }),
    [card, trace, extensions],
  );

  const visibleSteps = useMemo(
    () => filterVisibleWorkflowSteps(card.steps),
    [card.steps],
  );

  const liveThink = trace?.thinkContent?.trim() ?? "";
  // 不要在 isRunning 变化的瞬间从 liveThink 切到 pinnedThink，否则用户会看到内容
  // "刷新"一下。pinnedThink 是 backend 在 stage 结束时下发的快照，理论上 >= liveThink；
  // 取两者中"信息量更大"的那个，保证流式过程到结束的内容不闪烁、不回退。
  const thinkForCard = pinnedThink && pinnedThink.length >= liveThink.length
    ? pinnedThink
    : liveThink;
  const hasThinkStream =
    (card.type === "understand" ||
      card.type === "brief" ||
      card.type === "search") &&
    Boolean(thinkForCard || (streaming && isRunning));

  const headStatus = cardHeadStatus(card, isRunning, hasThinkStream);

  return (
    <section
      className={`litpilot-wf-card litpilot-wf-card--${card.state}${
        open ? " litpilot-wf-card--open" : ""
      }${streaming && isRunning ? " litpilot-wf-card--live" : ""}`}
    >
      <div className="litpilot-wf-card__head">
        <span className="litpilot-wf-card__marker">
          <StatusIcon status={headStatus} />
        </span>
        {canToggle ? (
          <button
            type="button"
            className="litpilot-wf-card__title-btn"
            onClick={() => setUserIntent((prev) => (prev !== null ? !prev : !systemOpen))}
            aria-expanded={open}
          >
            {card.title}
          </button>
        ) : (
          <span className="litpilot-wf-card__title">{card.title}</span>
        )}
        {cardSummary ? (
          <span className="litpilot-wf-card__inline-summary">{cardSummary}</span>
        ) : null}
      </div>
      {open ? (
        <div className="litpilot-wf-card__body">
          {(card.type === "understand" ||
            card.type === "brief" ||
            card.type === "search") &&
          (thinkForCard || (streaming && isRunning)) ? (
            <LitPilotThinkFold
              content={thinkForCard}
              streaming={streaming && isRunning}
              turnStreaming={streaming}
            />
          ) : null}
          {/* understand / search 的全部内容由上方 thinkfold 渲染；只有 brief 在
              thinkfold 之外保留结构化 RQ+关键词 body。其它非 think-stream 卡片
              （如 outline / generate）的 body 正常渲染。 */}
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
              extensions={extensions}
              subTopics={card.subTopics}
              streaming={streaming && isRunning}
            />
          ) : null}
          {card.type === "fetch" && card.subsectionSteps?.length ? (
            <div className="litpilot-wf-subsections">
              <FetchSubsectionBlock
                label="文献获取"
                steps={card.steps}
                trace={trace}
              />
              <FetchSubsectionBlock
                label="引用抽取"
                steps={card.subsectionSteps}
                trace={trace}
              />
            </div>
          ) : (
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
          )}
        </div>
      ) : null}
    </section>
  );
}
