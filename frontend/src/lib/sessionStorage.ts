export const ACTIVE_SESSION_STORAGE_KEY = "litpilot:active-session";

export function persistActiveSession(sessionId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
}
