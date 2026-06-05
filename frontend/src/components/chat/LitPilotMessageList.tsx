"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type RefObject,
} from "react";
import { ChatBubble } from "@meso.ai/ui";
import type { StreamState } from "@meso.ai/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { LitPilotAssistantTurn } from "./LitPilotAssistantTurn";
import { LitPilotProcessTrace } from "./LitPilotProcessTrace";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";

const SCROLL_BOTTOM_THRESHOLD_PX = 80;

function isNearScrollBottom(el: HTMLElement): boolean {
  return (
    el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD_PX
  );
}

export type LitPilotMessageListProps = {
  messages: LitPilotMessage[];
  streaming?: StreamState;
  emptyState?: React.ReactNode;
  emptyStateAlign?: "center" | "top";
  /** Scrollable ancestor (e.g. `.litpilot-chat-scroll`). */
  scrollContainerRef?: RefObject<HTMLElement | null>;
  /** When this changes, re-pin to bottom (e.g. active session id). */
  scrollResetKey?: string | null;
};

export function LitPilotMessageList({
  messages,
  streaming,
  emptyState,
  emptyStateAlign = "center",
  scrollContainerRef,
  scrollResetKey,
}: LitPilotMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const prevMessageCountRef = useRef(messages.length);

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = "auto") => {
      const el = scrollContainerRef?.current;
      if (el) {
        el.scrollTo({ top: el.scrollHeight, behavior });
        return;
      }
      bottomRef.current?.scrollIntoView({ behavior });
    },
    [scrollContainerRef],
  );

  useEffect(() => {
    const el = scrollContainerRef?.current;
    if (!el) return;

    const onScroll = () => {
      stickToBottomRef.current = isNearScrollBottom(el);
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scrollContainerRef]);

  useEffect(() => {
    stickToBottomRef.current = true;
    scrollToBottom("auto");
  }, [scrollResetKey, scrollToBottom]);

  useEffect(() => {
    const prevCount = prevMessageCountRef.current;
    if (messages.length > prevCount) {
      const last = messages[messages.length - 1];
      if (last?.role === "user") {
        stickToBottomRef.current = true;
      }
    }
    prevMessageCountRef.current = messages.length;
  }, [messages]);

  const liveTrace = useMemo(
    () =>
      streaming && streaming.status !== "idle"
        ? collectExecutionTraceFromStream(streaming)
        : null,
    [streaming],
  );

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    const streamingActive = streaming?.status === "streaming";
    scrollToBottom(streamingActive ? "auto" : "smooth");
  }, [messages, streaming, scrollToBottom]);

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
