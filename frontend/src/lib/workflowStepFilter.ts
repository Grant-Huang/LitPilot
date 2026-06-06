import type { WorkflowStep } from "@/lib/turnWorkflow";

/** 去掉已被 tool 步覆盖的 transient inline 步（检索中/抓取中） */
export function filterVisibleWorkflowSteps(steps: WorkflowStep[]): WorkflowStep[] {
  const doneSearchPasses = new Set<number>();

  for (const step of steps) {
    if (step.kind !== "tool") continue;
    if (!step.title.includes("检索")) continue;
    const m = /（(\d+)\/(\d+)）/.exec(step.title);
    if (m && step.status === "done") doneSearchPasses.add(parseInt(m[1], 10));
    else if (step.status === "done") doneSearchPasses.add(1);
  }

  return steps.filter((step) => {
    if (step.kind !== "inline") return true;
    if (step.key.startsWith("ext-literature_search_pass_start")) {
      const pi = parseInt(step.key.split("-").pop() ?? "0", 10);
      if (doneSearchPasses.has(pi)) return false;
    }
    if (step.key.startsWith("ext-literature_fetch_start")) {
      const urlKey = step.key.replace("ext-literature_fetch_start-", "");
      const hasTool = steps.some(
        (s) =>
          s.kind === "tool" &&
          s.status !== "pending" &&
          (s.title.includes(urlKey.slice(0, 32)) || s.key.includes(urlKey.slice(0, 16))),
      );
      if (hasTool) return false;
    }
    return true;
  });
}

export function formatInlineLogLine(step: WorkflowStep): {
  primary: string;
  outcome: string | null;
} {
  const pending = step.status === "running" || step.status === "pending";
  return {
    primary: step.title,
    outcome: pending ? "进行中…" : step.preview ?? null,
  };
}
