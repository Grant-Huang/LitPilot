export type ApiEnvelope<T> = {
  status: "success" | "error";
  data?: T;
  message?: string;
};

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("/api") ? path : `/api${path}`;
  return fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
}

export async function apiRequestData<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  const body = (await res.json()) as ApiEnvelope<T>;
  if (!res.ok || body.status === "error") {
    throw new Error(body.message || `HTTP ${res.status}`);
  }
  return body.data as T;
}
