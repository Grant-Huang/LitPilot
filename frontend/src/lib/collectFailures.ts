import type { StreamState } from "@meso/ui";
import { describeToolAction } from "@/lib/toolLabels";

export type FailedLiteratureItem = {
  url: string;
  title?: string;
  reason: string;
  kind: string;
};

export function collectFailuresFromStream(
  stream: StreamState,
): FailedLiteratureItem[] {
  const seen = new Set<string>();
  const items: FailedLiteratureItem[] = [];

  const push = (item: FailedLiteratureItem) => {
    const key = `${item.kind}|${item.url}|${item.reason}`;
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  };

  for (const id of stream.toolCallOrder) {
    const tc = stream.toolCalls[id];
    if (!tc || tc.status !== "error") continue;
    const url = String(tc.call.args?.url ?? "").trim();
    push({
      url: url || describeToolAction(tc.call),
      title: String(tc.call.args?.title ?? "").trim() || undefined,
      reason: tc.result?.error || "执行失败",
      kind: describeToolAction(tc.call),
    });
  }

  for (const runId of stream.workflowRunOrder) {
    const run = stream.workflowRuns[runId];
    if (!run) continue;
    for (const nodeId of run.nodeOrder) {
      const node = run.nodes[nodeId];
      if (!node || node.state !== "error") continue;
      const meta = node.metadata ?? {};
      const url = String(meta.url ?? "").trim();
      push({
        url: url || node.name || nodeId,
        title: String(meta.title ?? "").trim() || undefined,
        reason: String(meta.error ?? "抓取或处理失败"),
        kind: node.name === "web_fetch" ? "抓取网页" : node.name,
      });
    }
  }

  return items;
}
