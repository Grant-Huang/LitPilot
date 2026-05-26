"use client";

import { useMemo } from "react";
import { ChatBubble } from "@meso/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { mergeThinkIntoTrace } from "@/lib/executionTrace";
import { renderSimpleMarkdown } from "@/lib/simpleMarkdown";
import { LitPilotProcessTrace } from "./LitPilotProcessTrace";
import { LitPilotFailedList } from "./LitPilotFailedList";

type Props = {
  message: LitPilotMessage;
};

export function LitPilotAssistantTurn({ message }: Props) {
  const extras = message.extras;
  const trace = useMemo(
    () =>
      mergeThinkIntoTrace(extras?.executionTrace, extras?.thinkContent),
    [extras?.executionTrace, extras?.thinkContent],
  );

  return (
    <div className="litpilot-assistant-turn">
      {trace ? (
        <LitPilotProcessTrace trace={trace} defaultCollapsed />
      ) : (
        <>
          {extras?.failedLiterature && extras.failedLiterature.length > 0 ? (
            <LitPilotFailedList items={extras.failedLiterature} />
          ) : null}
        </>
      )}
      {message.content ? (
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
