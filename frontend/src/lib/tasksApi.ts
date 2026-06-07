import { apiRequestData } from "@/lib/http";
import type { LiteratureTaskStatusRow } from "@/lib/taskTypes";

export type CreateLiteratureTaskBody = {
  message: string;
  session_id?: string;
  fetch_urls?: string[];
  literature_source_mode?: "merge" | "user_only";
};

export const tasksApi = {
  create(body: CreateLiteratureTaskBody): Promise<LiteratureTaskStatusRow> {
    return apiRequestData<LiteratureTaskStatusRow>("/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  status(taskId: string): Promise<LiteratureTaskStatusRow> {
    return apiRequestData<LiteratureTaskStatusRow>(
      `/tasks/${taskId}/status`,
      { method: "GET" },
      8_000,
    );
  },

  cancel(taskId: string): Promise<LiteratureTaskStatusRow> {
    return apiRequestData<LiteratureTaskStatusRow>(`/tasks/${taskId}`, {
      method: "DELETE",
    });
  },

  active(): Promise<{ items: LiteratureTaskStatusRow[] }> {
    return apiRequestData<{ items: LiteratureTaskStatusRow[] }>(
      "/tasks/active",
      { method: "GET" },
      8_000,
    );
  },
};
