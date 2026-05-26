import type { Message } from "@meso/ui";
import type { FailedLiteratureItem } from "@/lib/collectFailures";
import type { ExecutionTrace } from "@/lib/executionTrace";

export type AssistantTurnExtras = {
  thinkContent?: string;
  failedLiterature?: FailedLiteratureItem[];
  executionTrace?: ExecutionTrace;
};

export type LitPilotMessage = Message & {
  extras?: AssistantTurnExtras;
};
