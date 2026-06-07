import { apiRequestData } from "@/lib/http";

export type PersonalPreferences = {
  citation_format: "apa" | "acm";
  plan_confirm: boolean;
};

export type StorageSettings = {
  backend: string;
  data_dir: string;
  tenant_id: string;
  database_url: string;
  database_url_source: string;
  has_auth_token: boolean;
  masked_auth_token: string;
  auth_token_source: string;
  turso_ready: boolean;
  turso_configured: boolean;
  admin_has_url: boolean;
  admin_has_token: boolean;
  env_has_url: boolean;
  env_has_token: boolean;
};

export type SystemOverview = {
  credentials: Array<Record<string, unknown>>;
  instances: Array<Record<string, unknown>>;
  capabilities: Array<{
    capability_id: string;
    label: string;
    enabled: boolean;
    ok: boolean;
    primary_ref: Record<string, unknown> | null;
  }>;
  storage: StorageSettings;
};

export type SystemCapability = {
  capability_id: string;
  label: string;
  enabled: boolean;
  primary_ref: Record<string, unknown> | null;
  override_params: Record<string, unknown>;
  params: Record<string, unknown>;
};

export type PromptTemplateMeta = {
  key: string;
  label: string;
  group: string;
  group_label: string;
  instance_binding?: string | null;
  max_len: number;
  default_max_tokens?: number;
  max_tokens_limit?: number;
  hint: string;
};

export type PromptTemplateDefaults = {
  defaults: Record<string, string>;
  meta: PromptTemplateMeta[];
};

export type SystemCredential = {
  id: string;
  type: string;
  name: string;
  has_secret: boolean;
  masked_secret: string;
  base_url?: string;
  group_id?: string;
  status?: string;
  last_verified_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type SystemInstance = {
  id: string;
  name: string;
  provider: string;
  credential_id: string;
  model_name: string;
  default_params: Record<string, unknown>;
  status?: string;
  last_verified_at?: string | null;
  created_at?: string;
  updated_at?: string;
};

export const settingsApiV2 = {
  getPersonalPreferences: () =>
    apiRequestData<PersonalPreferences>("/settings/personal/preferences"),
  savePersonalPreferences: (partial: Partial<PersonalPreferences>) =>
    apiRequestData<PersonalPreferences>("/settings/personal/preferences", {
      method: "PUT",
      body: JSON.stringify(partial),
    }),
  getSystemOverview: () => apiRequestData<SystemOverview>("/settings/system/overview"),
  getSystemStorage: () => apiRequestData<StorageSettings>("/settings/system/storage"),
  saveSystemStorage: (body: { database_url?: string; auth_token?: string }) =>
    apiRequestData<StorageSettings>("/settings/system/storage", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  getSystemCapabilities: () =>
    apiRequestData<{ items: SystemCapability[] }>("/settings/system/capabilities"),
  getPromptDefaults: () =>
    apiRequestData<PromptTemplateDefaults>("/settings/system/prompts/defaults"),

  listCredentials: () =>
    apiRequestData<{ items: SystemCredential[] }>("/settings/system/credentials"),
  createCredential: (body: {
    name: string;
    type: string;
    secret?: string;
    base_url?: string;
    group_id?: string;
  }) =>
    apiRequestData<SystemCredential>("/settings/system/credentials", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateCredential: (id: string, body: Partial<{ name: string; secret: string; base_url: string; group_id: string }>) =>
    apiRequestData<SystemCredential>(`/settings/system/credentials/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteCredential: (id: string) =>
    apiRequestData<{ deleted: boolean }>(`/settings/system/credentials/${id}`, {
      method: "DELETE",
    }),
  testCredential: (id: string, body?: { query?: string }) =>
    apiRequestData<{
      credential: SystemCredential;
      ok?: boolean;
      hits?: number;
      note?: string;
    }>(`/settings/system/credentials/${id}/test`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),

  listInstances: () =>
    apiRequestData<{ items: SystemInstance[] }>("/settings/system/instances"),
  createInstance: (body: {
    name: string;
    provider: string;
    credential_id: string;
    model_name: string;
    default_params?: Record<string, unknown>;
  }) =>
    apiRequestData<SystemInstance>("/settings/system/instances", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateInstance: (
    id: string,
    body: Partial<{
      name: string;
      credential_id: string;
      model_name: string;
      default_params: Record<string, unknown>;
    }>,
  ) =>
    apiRequestData<SystemInstance>(`/settings/system/instances/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteInstance: (id: string) =>
    apiRequestData<{ deleted: boolean }>(`/settings/system/instances/${id}`, {
      method: "DELETE",
    }),
  testInstance: (id: string) =>
    apiRequestData<{ ok?: boolean; note?: string; instance?: SystemInstance }>(
      `/settings/system/instances/${id}/test`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    ),

  updateCapability: (
    capability_id: string,
    body: Partial<{
      enabled: boolean;
      primary_ref: Record<string, unknown> | null;
      override_params: Record<string, unknown>;
      params: Record<string, unknown>;
    }>,
  ) =>
    apiRequestData<SystemCapability>(`/settings/system/capabilities/${capability_id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  testWebFetchUrl: (body: {
    url: string;
    provider?: string;
    pdf_extract_backend?: string;
  }) =>
    apiRequestData<{
      ok: boolean;
      provider: string;
      url: string;
      final_url?: string;
      resolved_pdf_url?: string | null;
      is_pdf?: boolean;
      pdf_extract_backend?: string | null;
      raw_bytes: number;
      text_chars: number;
      title?: string;
      preview?: string;
      note?: string;
      message?: string;
    }>("/settings/system/capabilities/web_fetch/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  testWebSearch: (body: { query: string; provider?: string }) =>
    apiRequestData<{
      ok: boolean;
      provider: string;
      query: string;
      hits: number;
      note?: string;
      results?: Array<{ title?: string; url?: string }>;
    }>("/settings/system/capabilities/web_search/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

