"use client";

import { useMemo } from "react";
import type { TurnWorkflow } from "@/lib/turnWorkflow";
import type { ExecutionTrace } from "@/lib/executionTrace";
import { buildTurnCompletionSummary } from "@/lib/turnCompletion";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";
import { TurnCompletionBar } from "./TurnCompletionBar";
import { WorkflowCardView } from "./WorkflowCardView";
import { StatusIcon } from "./StatusIcon";

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
    const isSubsequentTurn = (workflow.turnIndex ?? 1) > 1;
    const pendingTitle = isSubsequentTurn ? "分析用户意图" : "理解研究问题";
    const pendingText = isSubsequentTurn ? "正在分析你的意图…" : "正在理解你的研究问题…";
    return (
      <div className="litpilot-turn-log litpilot-turn-log--pending">
        <div className="litpilot-turn-log__cards">
          <div className="litpilot-wf-card litpilot-wf-card--running litpilot-wf-card--open litpilot-wf-card--live">
            <div className="litpilot-wf-card__head">
              <span className="litpilot-wf-card__marker">
                <StatusIcon status="running" />
              </span>
              <span className="litpilot-wf-card__title">{pendingTitle}</span>
            </div>
            <div className="litpilot-wf-card__body">
              <div className="litpilot-log-lines" role="list">
                <div
                  className="litpilot-log-line litpilot-log-line--running"
                  role="listitem"
                >
                  <span className="litpilot-log-line__marker">
                    <StatusIcon status="running" />
                  </span>
                  <p className="litpilot-log-line__text">
                    <span className="litpilot-log-line__primary">
                      {liveProcessText.trim() || pendingText}
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="litpilot-turn-log">
      <div className="litpilot-turn-log__cards">
        {workflow.cards.map((card) => (
          <WorkflowCardView
            key={card.id}
            card={card}
            trace={trace}
            streaming={streaming}
            forceOpen={card.type === "clarify"}
            extensions={extensions}
          />
        ))}
      </div>
      {!streaming ? (
        <TurnCompletionBar
          summary={completion}
          streaming={false}
          hasArtifact={hasArtifact || bridge?.hasArtifact}
          artifactVisible={bridge?.artifactPanelVisible}
          onOpenArtifact={bridge?.openArtifactPanel}
        />
      ) : null}
    </div>
  );
}
