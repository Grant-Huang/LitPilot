"use client";

import { TurnWorkflowBlock } from "./TurnWorkflowBlock";
import type { StreamState } from "@meso.ai/ui";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import {
  buildTurnWorkflowFromStream,
  deriveLiveFieldsFromStream,
} from "@/lib/turnWorkflow";
import { ChatBubble } from "@meso.ai/ui";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { useChatLayoutBridgeOptional } from "@/contexts/ChatLayoutBridgeContext";

type LiveTurnProps = {
  streaming: StreamState;
  hasArtifact?: boolean;
};

export function LitPilotLiveTurn({
  streaming,
  hasArtifact = false,
}: LiveTurnProps) {
  const bridge = useChatLayoutBridgeOptional();
  const trace = collectExecutionTraceFromStream(streaming);
  const { intent, processText, chatText } = deriveLiveFieldsFromStream(streaming);
  const workflow = buildTurnWorkflowFromStream(streaming);
  const extensions = streaming.extensionLog.map((e) => ({
    name: e.payload.name,
    data: (e.payload.data ?? {}) as Record<string, unknown>,
  }));
  const showChat =
    intent === "query_corpus" ||
    workflow.clarifying ||
    Boolean(chatText.trim());

  return (
    <div className="meso-message-list__live litpilot-message-list__live">
      <TurnWorkflowBlock
        workflow={workflow}
        trace={trace}
        streaming={streaming.status === "streaming"}
        extensions={extensions}
        hasArtifact={hasArtifact || bridge?.hasArtifact}
        chatText={chatText}
        liveProcessText={processText}
      />
      {showChat && (chatText || streaming.status === "streaming") ? (
        <ChatBubble
          role="assistant"
          content={chatText}
          streaming={streaming.status === "streaming"}
          markdown
          renderMarkdown={renderSimpleMarkdown}
        />
      ) : null}
    </div>
  );
}
