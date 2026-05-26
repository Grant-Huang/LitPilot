import type { StreamState } from "@meso/ui";

/** 深拷贝流状态，用于正文出现后保留 Artifact 栏 */
export function cloneStreamState(state: StreamState): StreamState {
  return JSON.parse(JSON.stringify(state)) as StreamState;
}
