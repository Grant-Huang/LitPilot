/** 将 SSE 流状态物化为 assistant 消息，供 refetch 完成前兜底展示。 */
import type { StreamState } from "@meso.ai/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";
import { buildTurnWorkflowFromStream } from "@/lib/turnWorkflow";

export function materializeAssistantFromStream(
  stream: StreamState,
  opts?: { intent?: string; processText?: string; chatText?: string },
): LitPilotMessage | null {
  if (stream.status === "idle") return null;
  const trace = collectExecutionTraceFromStream(stream);
  const workflow = buildTurnWorkflowFromStream(stream, opts);
  const hasTrace =
    trace.stages.length > 0 ||
    trace.tools.length > 0 ||
    Boolean(trace.thinkContent?.trim());
  const chatText = opts?.chatText ?? "";
  if (!workflow.cards.length && !hasTrace && !chatText) return null;
  return {
    id: `stream-assistant-${Date.now()}`,
    role: "assistant",
    content: chatText,
    extras: {
      executionTrace: trace,
      thinkContent: stream.thinkContent || trace.thinkContent,
      turnWorkflow: workflow,
      delivery: opts?.intent === "query_corpus" ? "chat" : "process",
    },
  };
}
