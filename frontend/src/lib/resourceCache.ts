type CacheEntry<T> = {
  data?: T;
  ts: number;
  promise?: Promise<T>;
};

const stores = new Map<string, CacheEntry<unknown>>();

export function invalidateCachedResource(key: string): void {
  stores.delete(key);
}

export function peekCachedResource<T>(key: string, ttlMs: number): T | undefined {
  const row = stores.get(key) as CacheEntry<T> | undefined;
  if (!row?.data) return undefined;
  if (Date.now() - row.ts > ttlMs) return undefined;
  return row.data;
}

export function getCachedResource<T>(
  key: string,
  loader: () => Promise<T>,
  ttlMs = 30_000,
): Promise<T> {
  const cached = peekCachedResource<T>(key, ttlMs);
  if (cached !== undefined) return Promise.resolve(cached);

  const row = stores.get(key) as CacheEntry<T> | undefined;
  if (row?.promise) return row.promise;

  const promise = loader()
    .then((data) => {
      stores.set(key, { data, ts: Date.now() });
      return data;
    })
    .catch((e) => {
      const current = stores.get(key) as CacheEntry<T> | undefined;
      if (current?.promise === promise) stores.delete(key);
      throw e;
    });

  stores.set(key, {
    data: row?.data,
    ts: row?.ts ?? 0,
    promise,
  });
  return promise;
}
