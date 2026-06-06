export type LiteratureTaskStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type LiteratureTaskStage =
  | "starting"
  | "understanding"
  | "searching"
  | "fetching"
  | "analyzing"
  | "writing"
  | "completed";

export type ActiveLiteratureTask = {
  taskId: string;
  sessionId: string;
  status: LiteratureTaskStatus;
  progress: number;
  stage: string;
  startedAt: number;
  lastEventSeq: number;
  error?: string;
  notified?: boolean;
};

export type LiteratureTaskStatusRow = {
  task_id: string;
  session_id: string;
  status: LiteratureTaskStatus;
  progress: number;
  stage: string;
  error?: string | null;
  event_count: number;
  started_at?: number;
  finished_at?: number | null;
};

export function mapStatusRow(row: LiteratureTaskStatusRow): ActiveLiteratureTask {
  return {
    taskId: row.task_id,
    sessionId: row.session_id,
    status: row.status,
    progress: row.progress,
    stage: row.stage,
    startedAt: row.started_at ? Math.floor(row.started_at * 1000) : Date.now(),
    lastEventSeq: row.event_count ?? 0,
    error: row.error ?? undefined,
  };
}

export function isTerminalTaskStatus(status: LiteratureTaskStatus): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

export function isRunningTaskStatus(status: LiteratureTaskStatus): boolean {
  return status === "pending" || status === "running";
}
