"use client";

import { TurnWorkflowBlock } from "./TurnWorkflowBlock";
import type { LitPilotMessage } from "@/lib/chatTypes";
import type { StreamState } from "@meso.ai/ui";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { buildTurnWorkflowFromStream } from "@/lib/turnWorkflow";
import { ChatBubble } from "@meso.ai/ui";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";

type LiveTurnProps = {
  streaming: StreamState;
  liveIntent: string;
  liveProcessText: string;
  liveChatText: string;
  hasArtifact?: boolean;
};

export function LitPilotLiveTurn({
  streaming,
  liveIntent,
  liveProcessText,
  liveChatText,
  hasArtifact = false,
}: LiveTurnProps) {
  const bridge = useChatLayoutBridgeOptional();
  const trace = collectExecutionTraceFromStream(streaming);
  const workflow = buildTurnWorkflowFromStream(streaming, {
    intent: liveIntent,
    processText: liveProcessText,
    chatText: liveChatText,
  });
  const extensions = streaming.extensionLog.map((e) => ({
    name: e.payload.name,
    data: (e.payload.data ?? {}) as Record<string, unknown>,
  }));
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
        extensions={extensions}
        hasArtifact={hasArtifact || bridge?.hasArtifact}
        chatText={liveChatText}
        liveProcessText={liveProcessText}
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
