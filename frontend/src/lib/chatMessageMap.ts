/** Map stored chat messages to LitPilot UI message model. */
import type { ChatMessage } from "@/lib/api";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { mergeThinkIntoTrace } from "@/lib/executionTrace";

export function chatMessagesToLitPilot(msgs: ChatMessage[]): LitPilotMessage[] {
  return msgs.map((m, i) => {
    const meta = m.meta;
    const failed = meta?.failed_literature;
    const think = meta?.think || meta?.thinkContent;
    const trace = mergeThinkIntoTrace(meta?.execution_trace, think);
    const hasExtras =
      m.role === "assistant" && (think || failed?.length || trace);
    return {
      id: `hist-${i}`,
      role: m.role as "user" | "assistant",
      content: m.content,
      extras: hasExtras
        ? {
            thinkContent: think,
            failedLiterature: failed,
            executionTrace: trace,
          }
        : undefined,
    };
  });
}
