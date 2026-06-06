"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCachedResource,
  invalidateCachedResource,
  peekCachedResource,
} from "@/lib/resourceCache";

type Options = {
  ttlMs?: number;
  enabled?: boolean;
};

export function useCachedResource<T>(
  key: string,
  loader: () => Promise<T>,
  options?: Options,
) {
  const ttlMs = options?.ttlMs ?? 30_000;
  const enabled = options?.enabled ?? true;
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const [data, setData] = useState<T | undefined>(() =>
    enabled ? peekCachedResource<T>(key, ttlMs) : undefined,
  );
  const [loading, setLoading] = useState(() => {
    if (!enabled) return false;
    return peekCachedResource<T>(key, ttlMs) === undefined;
  });
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    invalidateCachedResource(key);
    setLoading(true);
    setError(null);
    void getCachedResource(key, () => loaderRef.current(), ttlMs)
      .then((next) => setData(next))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setLoading(false));
  }, [key, ttlMs]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const cached = peekCachedResource<T>(key, ttlMs);
    if (cached !== undefined) {
      setData(cached);
      setLoading(false);
      return;
    }
    setLoading(true);
    void getCachedResource(key, () => loaderRef.current(), ttlMs)
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, key, ttlMs]);

  return { data, loading, error, refresh, setData };
}
