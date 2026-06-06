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
  defaultCollapsed?: boolean;
  extensions?: Array<{ name: string; data: Record<string, unknown> }>;
  hasArtifact?: boolean;
  chatText?: string;
};

export function TurnWorkflowBlock({
  workflow,
  trace,
  streaming = false,
  extensions = [],
  hasArtifact = false,
  chatText = "",
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
      }),
    [workflow, trace, extensions, hasArtifact, chatText],
  );

  if (!workflow.cards.length) return null;

  const showCompletionBar = !workflow.clarifying;

  return (
    <div className="litpilot-turn-log">
      {showCompletionBar ? (
        <TurnCompletionBar
          summary={completion}
          streaming={streaming}
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
