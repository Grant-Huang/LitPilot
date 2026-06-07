import { apiRequestData } from "@/lib/http";
import type { ExecutionTrace } from "@/lib/executionTrace";
import type { LibraryItem } from "@/lib/libraryTypes";

export type SessionMeta = {
  id: string;
  title: string;
  updated_at?: string;
  created_at?: string;
  pinned?: boolean;
};

export type FailedLiteratureMeta = {
  url: string;
  title?: string;
  reason: string;
  kind: string;
};

import type { TurnWorkflow } from "@/lib/turnWorkflow";

export type ChatMessage = {
  role: string;
  content: string;
  ts?: string;
  meta?: {
    think?: string;
    thinkContent?: string;
    failed_literature?: FailedLiteratureMeta[];
    execution_trace?: ExecutionTrace;
    turn_workflow?: TurnWorkflow;
    delivery?: "chat" | "process";
    artifact_kind?: "review" | "matrix";
    intent?: string;
  };
};

export type AgentSettings = {
  web_search_api_key?: string;
  fetch_api_key?: string;
  llm_provider?: string;
  llm_api_key?: string;
  llm_model?: string;
  llm_base_url?: string;
  fetch_parallel?: number;
  fetch_timeout_sec?: number;
  search_max_results?: number;
  max_fetch_urls?: number;
  literature_source_mode?: "merge" | "user_only";
  search_retry_count?: number;
  fetch_retry_count?: number;
  fetch_retry_delay_ms?: number;
  citation_format?: "apa" | "acm";
  llm_group_id?: string;
  has_web_search?: boolean;
  has_fetch?: boolean;
  has_llm?: boolean;
  use_llm_planner?: boolean;
  orchestrator_mode?: "off" | "lite" | "full";
  orchestrator_use_reasoning?: boolean;
  orchestrator_model?: string;
  orchestrator_max_tokens_per_phase?: number;
  /** 自定义综述生成 system prompt；空字符串表示使用内置默认 */
  review_system_prompt_template?: string;
  /** 内置默认模板（含 {fmt_label}、{citation_format} 占位符） */
  review_system_prompt_default?: string;
};

export type RefIndex = {
  refs: Array<{
    index: number;
    apa: string;
    citation?: string;
    format?: "apa" | "acm";
    title: string;
    authors: string;
    year: string;
    url: string;
    doi: string;
  }>;
};

export const sessionsApi = {
  list: () => apiRequestData<SessionMeta[]>("/sessions"),
  create: (title?: string) =>
    apiRequestData<SessionMeta>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title: title || "新综述" }),
    }),
  delete: (id: string) =>
    apiRequestData<{ deleted: string }>(`/sessions/${id}`, { method: "DELETE" }),
  update: (id: string, body: { title?: string; pinned?: boolean }) =>
    apiRequestData<SessionMeta>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  get: (id: string) => apiRequestData<SessionMeta & { review_versions?: unknown[] }>(`/sessions/${id}`),
  messages: (id: string) =>
    apiRequestData<ChatMessage[]>(`/sessions/${id}/messages`),
  review: (id: string) =>
    apiRequestData<{
      filename: string;
      content: string;
      updated_at?: string;
    } | null>(`/sessions/${id}/review`),
  reviewVersion: (id: string, filename: string) =>
    apiRequestData<{
      filename: string;
      content: string;
      updated_at?: string;
    }>(`/sessions/${id}/review/${encodeURIComponent(filename)}`),
  matrix: (id: string) =>
    apiRequestData<{
      filename: string;
      content: string;
      updated_at?: string;
    } | null>(`/sessions/${id}/matrix`),
};

export const settingsApi = {
  getAgent: () => apiRequestData<AgentSettings>("/settings/agent"),
  saveAgent: (body: Partial<AgentSettings>) =>
    apiRequestData<AgentSettings>("/settings/agent", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export const LIBRARY_LIST_TIMEOUT_MS = 30_000;

export const libraryApi = {
  items: () =>
    apiRequestData<{ items: LibraryItem[]; total: number }>(
      "/library/items",
      undefined,
      LIBRARY_LIST_TIMEOUT_MS,
    ),
  item: (id: string) =>
    apiRequestData<{ item: LibraryItem; full_text: string }>(
      `/library/items/${encodeURIComponent(id)}`,
    ),
  refs: () =>
    apiRequestData<{
      index: RefIndex;
      ref_list_text: string;
      items?: LibraryItem[];
    }>("/library/refs"),
  pdfs: () => apiRequestData<{ files: string[] }>("/library/pdfs"),
  reconcile: (body: {
    session_id?: string;
    mode?: "session" | "all" | "failed_only";
  }) =>
    apiRequestData<Record<string, number>>("/library/reconcile", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  dedupe: () =>
    apiRequestData<Record<string, number>>("/library/dedupe", {
      method: "POST",
    }),
  migrate: () =>
    apiRequestData<Record<string, number>>("/library/migrate", {
      method: "POST",
    }),
  enrich: (itemId: string) =>
    apiRequestData<{
      ok: boolean;
      citation_count?: number;
      references_count?: number;
      item?: LibraryItem;
    }>(`/library/items/${encodeURIComponent(itemId)}/enrich`, { method: "POST" }),
  refreshMetadata: (body?: { item_ids?: string[]; parallel?: number }) =>
    apiRequestData<{ updated: number; skipped: number; total: number }>(
      "/library/refresh-metadata",
      {
        method: "POST",
        body: JSON.stringify(body || {}),
      },
    ),
  updateMetadata: (
    itemId: string,
    body: {
      title?: string;
      authors?: string[];
      year?: string;
      venue?: string;
      doi?: string;
      publisher?: string;
      abstract?: string;
      volume?: string;
      issue?: string;
      pages?: string;
      month?: string;
      refresh_crossref?: boolean;
    },
  ) =>
    apiRequestData<{ item: LibraryItem }>(
      `/library/items/${encodeURIComponent(itemId)}/metadata`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),
  star: (itemId: string, starred: boolean) =>
    apiRequestData<{ item: LibraryItem }>(
      `/library/items/${encodeURIComponent(itemId)}/star`,
      {
        method: "PATCH",
        body: JSON.stringify({ starred }),
      },
    ),
  delete: (itemId: string) =>
    apiRequestData<{ deleted: boolean; item_id: string }>(
      `/library/items/${encodeURIComponent(itemId)}`,
      { method: "DELETE" },
    ),
  relatedSessions: (itemId: string) =>
    apiRequestData<{
      sessions: {
        session_id: string;
        session_title: string;
        first_question: string;
        review_ref_index?: number | null;
      }[];
    }>(`/library/items/${encodeURIComponent(itemId)}/related-sessions`),
  tags: () =>
    apiRequestData<{ tags: { name: string; count: number }[] }>("/library/tags"),
  updateTags: (itemId: string, tags: string[]) =>
    apiRequestData<{ item: LibraryItem }>(
      `/library/items/${encodeURIComponent(itemId)}/tags`,
      {
        method: "PATCH",
        body: JSON.stringify({ tags }),
      },
    ),
};
