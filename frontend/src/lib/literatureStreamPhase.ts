import type { StreamState } from "@meso.ai/ui";

export type LiteratureStreamPhase =
  | "idle"
  | "pending"
  | "streaming"
  | "settling"
  | "done"
  | "error";

export function computeLiteratureStreamPhase(
  sseStatus: StreamState["status"],
  pending: boolean,
  settling: boolean,
): LiteratureStreamPhase {
  if (settling) return "settling";
  if (pending) return "pending";
  if (sseStatus === "streaming") return "streaming";
  if (sseStatus === "done") return "done";
  if (sseStatus === "error") return "error";
  return "idle";
}

export function isLiteratureStreamBusy(phase: LiteratureStreamPhase): boolean {
  return phase === "pending" || phase === "streaming" || phase === "settling";
}

export function isLiteratureStreamActive(phase: LiteratureStreamPhase): boolean {
  return (
    phase === "pending" ||
    phase === "streaming" ||
    phase === "settling" ||
    phase === "done" ||
    phase === "error"
  );
}
