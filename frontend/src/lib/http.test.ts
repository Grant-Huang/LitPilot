import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiFetch,
  apiTimeoutMessage,
} from "./http";

describe("apiFetch timeout", () => {
  it("throws ApiError 408 when request exceeds timeout", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return;
        if (signal.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        signal.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/library/items", undefined, 50)).rejects.toMatchObject({
      name: "ApiError",
      status: 408,
      message: apiTimeoutMessage(50),
    });

    vi.unstubAllGlobals();
  });

  it("maps timeout message with seconds", () => {
    expect(apiTimeoutMessage(15_000)).toContain("15 秒");
  });
});

describe("ApiError", () => {
  it("preserves status and data", () => {
    const err = new ApiError(502, "bad gateway", { detail: "x" });
    expect(err.status).toBe(502);
    expect(err.data).toEqual({ detail: "x" });
  });
});
