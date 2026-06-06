import type { ActiveLiteratureTask } from "@/lib/taskTypes";

export const ACTIVE_TASK_STORAGE_KEY = "litpilot:activeTask";

export function readStoredActiveTask(): ActiveLiteratureTask | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActiveLiteratureTask;
    if (!parsed?.taskId || !parsed?.sessionId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeStoredActiveTask(task: ActiveLiteratureTask | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!task) {
      sessionStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(ACTIVE_TASK_STORAGE_KEY, JSON.stringify(task));
  } catch {
    /* ignore quota / private mode */
  }
}
