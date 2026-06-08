"use client";

import { useMemo } from "react";
import type { TurnWorkflow } from "@/lib/turnWorkflow";
import type { ExecutionTrace } from "@/lib/executionTrace";
import { buildTurnCompletionSummary } from "@/lib/turnCompletion";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";
import { TurnCompletionBar } from "./TurnCompletionBar";
import { WorkflowCardView } from "./WorkflowCardView";

type Props = {
  workflow: TurnWorkflow;
  trace?: ExecutionTrace;
  streaming?: boolean;
  extensions?: Array<{ name: string; data: Record<string, unknown> }>;
  hasArtifact?: boolean;
  chatText?: string;
  liveProcessText?: string;
};

export function TurnWorkflowBlock({
  workflow,
  trace,
  streaming = false,
  extensions = [],
  hasArtifact = false,
  chatText = "",
  liveProcessText = "",
}: Props) {
  const bridge = useChatLayoutBridgeOptional();
  const runningId = useMemo(() => {
    const running = workflow.cards.find((c) => c.state === "running");
    return running?.id ?? null;
  }, [workflow.cards]);

  const completion = useMemo(
    () =>
      buildTurnCompletionSummary(workflow, {
        trace,
        extensions,
        hasReview: hasArtifact,
        hasMatrix: hasArtifact,
        chatText,
        streaming,
      }),
    [workflow, trace, extensions, hasArtifact, chatText, streaming],
  );

  if (!workflow.cards.length) {
    if (!streaming) return null;
    return (
      <div className="litpilot-turn-log litpilot-turn-log--pending">
        <div className="litpilot-wf-card litpilot-wf-card--running litpilot-wf-card--open litpilot-wf-card--live">
          <div className="litpilot-wf-card__head">
            <span className="litpilot-wf-card__title">理解研究问题</span>
          </div>
          <div className="litpilot-wf-card__body">
            <div className="litpilot-log-lines" role="list">
              <div
                className="litpilot-log-line litpilot-log-line--running"
                role="listitem"
              >
                <span className="litpilot-log-line__marker" aria-hidden="true">
                  <span className="litpilot-log-line__spinner" />
                </span>
                <p className="litpilot-log-line__text">
                  <span className="litpilot-log-line__primary">
                    {liveProcessText.trim() || "正在连接并分析研究问题…"}
                  </span>
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="litpilot-turn-log">
      {!streaming ? (
        <TurnCompletionBar
          summary={completion}
          streaming={false}
          hasArtifact={hasArtifact || bridge?.hasArtifact}
          artifactVisible={bridge?.artifactPanelVisible}
          onOpenArtifact={bridge?.openArtifactPanel}
        />
      ) : null}
      <div className="litpilot-turn-log__cards">
        {workflow.cards.map((card) => (
          <WorkflowCardView
            key={card.id}
            card={card}
            trace={trace}
            streaming={streaming}
            defaultOpen={card.id === runningId}
            forceOpen={card.type === "clarify"}
            extensions={extensions}
          />
        ))}
      </div>
    </div>
  );
}
