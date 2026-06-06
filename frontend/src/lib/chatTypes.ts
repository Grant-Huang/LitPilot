import type { Message } from "@meso.ai/ui";
import type { FailedLiteratureItem } from "@/lib/collectFailures";
import type { ExecutionTrace } from "@/lib/executionTrace";
import type { TurnWorkflow } from "@/lib/turnWorkflow";

export type AssistantTurnExtras = {
  thinkContent?: string;
  failedLiterature?: FailedLiteratureItem[];
  executionTrace?: ExecutionTrace;
  turnWorkflow?: TurnWorkflow;
  delivery?: "chat" | "process";
  artifactKind?: "review" | "matrix";
};

export type LitPilotMessage = Message & {
  extras?: AssistantTurnExtras;
};
