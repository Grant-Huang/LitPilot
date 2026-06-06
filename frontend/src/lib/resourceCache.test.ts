import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getCachedResource,
  invalidateCachedResource,
  peekCachedResource,
} from "./resourceCache";

describe("resourceCache", () => {
  afterEach(() => {
    invalidateCachedResource("test:key");
    invalidateCachedResource("test:fail");
  });

  it("dedupes concurrent loads for the same key", async () => {
    const loader = vi.fn(async () => ({ n: 1 }));
    const [a, b] = await Promise.all([
      getCachedResource("test:key", loader, 60_000),
      getCachedResource("test:key", loader, 60_000),
    ]);
    expect(a).toEqual({ n: 1 });
    expect(b).toEqual({ n: 1 });
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("returns cached data within ttl", async () => {
    const loader = vi.fn(async () => "cached");
    await getCachedResource("test:key", loader, 60_000);
    const peek = peekCachedResource<string>("test:key", 60_000);
    expect(peek).toBe("cached");
    await getCachedResource("test:key", loader, 60_000);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("clears failed in-flight loads", async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce("ok");
    await expect(getCachedResource("test:fail", loader, 60_000)).rejects.toThrow(
      "boom",
    );
    await expect(getCachedResource("test:fail", loader, 60_000)).resolves.toBe(
      "ok",
    );
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
