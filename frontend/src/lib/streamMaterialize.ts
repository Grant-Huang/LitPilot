import type { StreamState } from "@meso.ai/ui";
import type { LitPilotMessage } from "@/lib/chatTypes";
import { collectExecutionTraceFromStream } from "@/lib/executionTrace";

/** 将 SSE 流状态物化为 assistant 消息，供 refetch 完成前兜底展示。 */
export function materializeAssistantFromStream(
  stream: StreamState,
): LitPilotMessage | null {
  if (stream.status === "idle") return null;
  const trace = collectExecutionTraceFromStream(stream);
  const hasTrace =
    trace.stages.length > 0 ||
    trace.tools.length > 0 ||
    trace.workflows.length > 0 ||
    Boolean(trace.thinkContent?.trim());
  const text = stream.textContent?.trim() || "";
  if (!text && !hasTrace) return null;
  return {
    id: `stream-assistant-${Date.now()}`,
    role: "assistant",
    content: text,
    extras: {
      executionTrace: trace,
      thinkContent: stream.thinkContent || trace.thinkContent,
    },
  };
}
