"use client";

import { useEffect, useMemo, useRef } from "react";
import { ChatBubble } from "@meso.ai/ui";
import type { StreamState } from "@meso.ai/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { LitPilotAssistantTurn } from "./LitPilotAssistantTurn";
import { LitPilotProcessTrace } from "./LitPilotProcessTrace";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";

export type LitPilotMessageListProps = {
  messages: LitPilotMessage[];
  streaming?: StreamState;
  emptyState?: React.ReactNode;
  emptyStateAlign?: "center" | "top";
};

export function LitPilotMessageList({
  messages,
  streaming,
  emptyState,
  emptyStateAlign = "center",
}: LitPilotMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const liveTrace = useMemo(
    () =>
      streaming && streaming.status !== "idle"
        ? collectExecutionTraceFromStream(streaming)
        : null,
    [streaming],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const hasContent =
    messages.length > 0 || (streaming && streaming.status !== "idle");

  const showLiveThink =
    Boolean(liveTrace?.thinkContent) &&
    streaming &&
    streaming.status !== "idle" &&
    !streaming.textContent?.trim();

  return (
    <div className="meso-message-list litpilot-message-list">
      <div className="meso-message-list__inner">
        {!hasContent && emptyState && (
          <div
            className={`meso-message-list__empty${
              emptyStateAlign === "top" ? " meso-message-list__empty--top" : ""
            }`}
          >
            {emptyState}
          </div>
        )}

        {messages.map((m) =>
          m.role === "assistant" && m.extras ? (
            <LitPilotAssistantTurn key={m.id} message={m} />
          ) : (
            <ChatBubble
              key={m.id}
              role={m.role}
              content={m.content}
              timestamp={m.timestamp}
              markdown={m.role === "assistant"}
              renderMarkdown={renderSimpleMarkdown}
            />
          ),
        )}

        {streaming && streaming.status !== "idle" && (
          <div className="meso-message-list__live litpilot-message-list__live">
            {liveTrace && (
              <LitPilotProcessTrace
                trace={liveTrace}
                thinkStreaming={
                  showLiveThink &&
                  streaming.status === "streaming" &&
                  !streaming.thinkDone
                }
              />
            )}

            {(streaming.textContent || streaming.status === "streaming") && (
              <ChatBubble
                role="assistant"
                content={streaming.textContent}
                streaming={streaming.status === "streaming"}
                markdown
                renderMarkdown={renderSimpleMarkdown}
              />
            )}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
