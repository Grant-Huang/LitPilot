export type ApiEnvelope<T> = {
  status: "success" | "error";
  data?: T;
  message?: string;
};

export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("/api") ? path : `/api${path}`;
  return fetch(url, {
    cache: "no-store",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
}

export async function apiRequestData<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  let body: ApiEnvelope<T> | null = null;
  try {
    body = (await res.json()) as ApiEnvelope<T>;
  } catch {
    body = null;
  }
  if (!res.ok || body?.status === "error") {
    const msg = body?.message || `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, body?.data);
  }
  return (body?.data ?? (undefined as unknown)) as T;
}
