/** Map stored chat messages to LitPilot UI message model. */
import type { ChatMessage } from "@/lib/api";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { mergeThinkIntoTrace } from "@/lib/executionTrace";
import {
  buildTurnWorkflowFromTrace,
  mergeTurnWorkflowMeta,
  type TurnWorkflow,
} from "@/lib/turnWorkflow";

function turnWorkflowFromMeta(meta: Record<string, unknown> | undefined): TurnWorkflow | undefined {
  const raw = meta?.turn_workflow;
  if (!raw || typeof raw !== "object") return undefined;
  return raw as TurnWorkflow;
}

export function chatMessagesToLitPilot(msgs: ChatMessage[]): LitPilotMessage[] {
  return msgs.map((m, i) => {
    const meta = m.meta;
    const failed = meta?.failed_literature;
    const think = meta?.think || meta?.thinkContent;
    const trace = mergeThinkIntoTrace(meta?.execution_trace, think);
    const turnWorkflow =
      mergeTurnWorkflowMeta(turnWorkflowFromMeta(meta), trace) ??
      (trace ? buildTurnWorkflowFromTrace(trace, { chatText: m.content }) : undefined);
    const hasExtras =
      m.role === "assistant" &&
      (think || failed?.length || trace || turnWorkflow);
    const delivery = meta?.delivery === "chat" ? "chat" : "process";
    const showContent =
      delivery === "chat" && m.content?.trim() && meta?.artifact_kind !== "review";
    return {
      id: `hist-${i}`,
      role: m.role as "user" | "assistant",
      content: showContent ? m.content : "",
      extras: hasExtras
        ? {
            thinkContent: think,
            failedLiterature: failed,
            executionTrace: trace,
            turnWorkflow,
            delivery,
            artifactKind: meta?.artifact_kind as "review" | "matrix" | undefined,
          }
        : undefined,
    };
  });
}
