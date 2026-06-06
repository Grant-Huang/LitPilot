import { describe, expect, it } from "vitest";
import {
  isRunningTaskStatus,
  isTerminalTaskStatus,
  mapStatusRow,
} from "./taskTypes";

describe("taskTypes", () => {
  it("maps status row to active task", () => {
    const task = mapStatusRow({
      task_id: "abc",
      session_id: "sess",
      status: "running",
      progress: 42,
      stage: "searching",
      event_count: 7,
      started_at: 1_700_000_000,
    });
    expect(task.taskId).toBe("abc");
    expect(task.sessionId).toBe("sess");
    expect(task.lastEventSeq).toBe(7);
  });

  it("classifies running and terminal statuses", () => {
    expect(isRunningTaskStatus("running")).toBe(true);
    expect(isRunningTaskStatus("completed")).toBe(false);
    expect(isTerminalTaskStatus("failed")).toBe(true);
    expect(isTerminalTaskStatus("pending")).toBe(false);
  });
});
