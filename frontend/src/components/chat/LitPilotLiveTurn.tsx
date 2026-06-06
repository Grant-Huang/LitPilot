"use client";

import { LitPilotAssistantTurn } from "./LitPilotAssistantTurn";
import { TurnWorkflowBlock } from "./TurnWorkflowBlock";
import type { LitPilotMessage } from "@/lib/chatTypes";
import type { StreamState } from "@meso.ai/ui";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { buildTurnWorkflowFromStream } from "@/lib/turnWorkflow";
import { ChatBubble } from "@meso.ai/ui";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";

type LiveTurnProps = {
  streaming: StreamState;
  liveIntent: string;
  liveProcessText: string;
  liveChatText: string;
};

export function LitPilotLiveTurn({
  streaming,
  liveIntent,
  liveProcessText,
  liveChatText,
}: LiveTurnProps) {
  const trace = collectExecutionTraceFromStream(streaming);
  const workflow = buildTurnWorkflowFromStream(streaming, {
    intent: liveIntent,
    processText: liveProcessText,
    chatText: liveChatText,
  });
  const showChat =
    liveIntent === "query_corpus" ||
    workflow.clarifying ||
    Boolean(liveChatText.trim());

  return (
    <div className="meso-message-list__live litpilot-message-list__live">
      <TurnWorkflowBlock
        workflow={workflow}
        trace={trace}
        streaming={streaming.status === "streaming"}
      />
      {showChat && (liveChatText || streaming.status === "streaming") ? (
        <ChatBubble
          role="assistant"
          content={liveChatText}
          streaming={streaming.status === "streaming"}
          markdown
          renderMarkdown={renderSimpleMarkdown}
        />
      ) : null}
    </div>
  );
}

export type { LitPilotMessage };
