"use client";

import { useMemo } from "react";
import { ChatBubble } from "@meso.ai/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { mergeThinkIntoTrace } from "@/lib/executionTrace";
import { buildTurnWorkflowFromTrace, mergeTurnWorkflowMeta } from "@/lib/turnWorkflow";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";
import { TurnWorkflowBlock } from "./TurnWorkflowBlock";
import { LitPilotFailedList } from "./LitPilotFailedList";

type Props = {
  message: LitPilotMessage;
};

export function LitPilotAssistantTurn({ message }: Props) {
  const bridge = useChatLayoutBridgeOptional();
  const extras = message.extras;
  const trace = useMemo(
    () =>
      mergeThinkIntoTrace(extras?.executionTrace, extras?.thinkContent),
    [extras?.executionTrace, extras?.thinkContent],
  );
  const workflow = useMemo(
    () =>
      mergeTurnWorkflowMeta(extras?.turnWorkflow, trace) ??
      (trace
        ? buildTurnWorkflowFromTrace(trace, {
            chatText: message.content,
            intent: extras?.delivery === "chat" ? "query_corpus" : undefined,
          })
        : null),
    [extras?.turnWorkflow, trace, message.content, extras?.delivery],
  );

  const showChat =
    extras?.delivery === "chat" &&
    Boolean(message.content?.trim()) &&
    extras?.artifactKind !== "review";

  return (
    <div className="litpilot-assistant-turn">
      {workflow ? (
        <TurnWorkflowBlock
          workflow={workflow}
          trace={trace}
          hasArtifact={Boolean(bridge?.hasArtifact || extras?.artifactKind)}
          chatText={message.content}
        />
      ) : trace ? null : (
        <>
          {extras?.failedLiterature && extras.failedLiterature.length > 0 ? (
            <LitPilotFailedList items={extras.failedLiterature} />
          ) : null}
        </>
      )}
      {showChat ? (
        <ChatBubble
          role="assistant"
          content={message.content}
          markdown
          renderMarkdown={renderSimpleMarkdown}
        />
      ) : null}
    </div>
  );
}
