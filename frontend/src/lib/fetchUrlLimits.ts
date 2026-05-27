/** 与后端 `MAX_FETCH_URLS_CAP` / `url_list._MAX_REQUEST_URLS` 一致 */
export const MAX_FETCH_URLS_CAP = 50;

export function clampFetchUrlLimit(value: number | undefined | null): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 5;
  return Math.max(1, Math.min(Math.floor(n), MAX_FETCH_URLS_CAP));
}
