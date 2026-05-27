import { createInitialStreamState } from "@meso.ai/ui/runtime";
import type { StreamState } from "@meso.ai/ui";

/** 将已保存的综述 Markdown 注入 Artifact 流状态 */
export function streamStateWithReview(
  content: string,
  filename = "review-latest.md",
): StreamState {
  const id = "review-saved";
  const base = createInitialStreamState();
  return {
    ...base,
    status: "done",
    artifactOrder: [id],
    artifacts: {
      [id]: {
        id,
        lang: "markdown",
        content,
        done: true,
      },
    },
  };
}

export function streamHasArtifactPane(state: StreamState | null): boolean {
  if (!state) return false;
  if (state.workflowRunOrder.length > 0) return true;
  const hasGraph = state.artifactOrder.some(
    (id) => state.artifacts[id]?.lang === "workflow-graph",
  );
  if (hasGraph) return true;
  return state.artifactOrder.some((id) => {
    const art = state.artifacts[id];
    return art?.lang !== "workflow-graph" && Boolean(art?.content?.trim());
  });
}

export function downloadTextFile(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
