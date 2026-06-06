export const DEFAULT_API_TIMEOUT_MS = 15_000;

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

export function apiTimeoutMessage(ms: number): string {
  return `请求超时（${Math.round(ms / 1000)} 秒），请检查后端是否已启动或网络是否正常。`;
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_API_TIMEOUT_MS,
): Promise<Response> {
  const url = path.startsWith("/api") ? path : `/api${path}`;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const upstreamSignal = init?.signal;
  const onUpstreamAbort = () => controller.abort();
  if (upstreamSignal) {
    if (upstreamSignal.aborted) controller.abort();
    else upstreamSignal.addEventListener("abort", onUpstreamAbort, { once: true });
  }
  try {
    return await fetch(url, {
      cache: "no-store",
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError" && !upstreamSignal?.aborted) {
      throw new ApiError(408, apiTimeoutMessage(timeoutMs));
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
    if (upstreamSignal) upstreamSignal.removeEventListener("abort", onUpstreamAbort);
  }
}

export async function apiRequestData<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_API_TIMEOUT_MS,
): Promise<T> {
  const res = await apiFetch(path, init, timeoutMs);
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
